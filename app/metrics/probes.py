from __future__ import annotations

import asyncio
import re
from typing import Any, Callable

from app.adapters.base import BaseAdapter
from app.core.models import AdapterRequest, AdapterResponse, MetricResult, ModelConfig
from app.metrics.base import completed, errored, skipped
from app.utils.token_estimator import ESTIMATOR_NAME, estimate_tokens

AdapterFactory = Callable[[ModelConfig], BaseAdapter]


def _error_from_response(response: AdapterResponse | None, fallback: str) -> dict:
    if response is None:
        return {"code": "request_error", "message": fallback}
    if response.error:
        return response.error
    return {"code": "request_error", "message": fallback, "http_status": response.http_status}


def _usage_prompt(usage: dict | None) -> int | None:
    if not usage:
        return None
    return usage.get("prompt_tokens") or usage.get("input_tokens")


def _usage_completion(usage: dict | None) -> int | None:
    if not usage:
        return None
    return usage.get("completion_tokens") or usage.get("output_tokens")


def _usage_total(usage: dict | None) -> int | None:
    if not usage:
        return None
    return usage.get("total_tokens")


_CACHE_CACHED_TOKEN_PATHS = (
    ("prompt_tokens_details", "cached_tokens"),
    ("input_tokens_details", "cached_tokens"),
    ("cached_tokens",),
    ("prompt_cached_tokens",),
    ("input_cached_tokens",),
    ("cached_input_tokens",),
    ("cache_read_input_tokens",),
)
_CACHE_CREATION_TOKEN_PATHS = (
    ("cache_creation_input_tokens",),
    ("prompt_cache_creation_tokens",),
)
_CACHE_HIT_PATHS = (
    ("cache_hit",),
    ("prompt_cache_hit",),
    ("input_cache_hit",),
)


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _get_nested(data: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = data
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _collect_usage_cache_paths(data: Any, prefix: tuple[str, ...] = ()) -> set[str]:
    if not isinstance(data, dict):
        return set()
    found: set[str] = set()
    for key, value in data.items():
        path = prefix + (str(key),)
        lowered = str(key).lower()
        if "cache" in lowered or "cached" in lowered:
            found.add(".".join(path))
        found.update(_collect_usage_cache_paths(value, path))
    return found


def _extract_cache_usage(usage: dict | None) -> dict[str, Any]:
    if not usage:
        return {
            "cached_tokens": None,
            "cache_creation_tokens": None,
            "cache_read_tokens": None,
            "cache_hit": None,
            "field_paths": [],
        }

    field_paths = _collect_usage_cache_paths(usage)

    cached_values: list[int] = []
    for path in _CACHE_CACHED_TOKEN_PATHS:
        value = _as_int(_get_nested(usage, path))
        if value is not None:
            cached_values.append(value)
            field_paths.add(".".join(path))

    creation_values: list[int] = []
    for path in _CACHE_CREATION_TOKEN_PATHS:
        value = _as_int(_get_nested(usage, path))
        if value is not None:
            creation_values.append(value)
            field_paths.add(".".join(path))

    read_value = _as_int(usage.get("cache_read_input_tokens"))
    if read_value is not None:
        field_paths.add("cache_read_input_tokens")

    hit: bool | None = None
    for path in _CACHE_HIT_PATHS:
        value = _get_nested(usage, path)
        if isinstance(value, bool):
            hit = hit or value if hit is not None else value
            field_paths.add(".".join(path))

    cached_tokens = max(cached_values) if cached_values else None
    creation_tokens = max(creation_values) if creation_values else None
    cache_read_tokens = read_value if read_value is not None else cached_tokens
    return {
        "cached_tokens": cached_tokens,
        "cache_creation_tokens": creation_tokens,
        "cache_read_tokens": cache_read_tokens,
        "cache_hit": hit,
        "field_paths": sorted(field_paths),
    }


def _cache_probe_target_tokens(config: ModelConfig) -> int:
    declared = config.declared_context_tokens
    if declared is None:
        return 4096
    if declared <= 2048:
        return max(256, declared // 2)
    return min(8192, max(1024, declared // 4))


def _build_cache_probe_prefix(target_tokens: int) -> str:
    block = (
        "缓存能力评测固定前缀。"
        "本段内容用于观察模型网关或上游模型是否复用相同 Prompt 前缀，"
        "请在后续回答时只根据最后的问题作答，不要复述本前缀。"
        "编号={index:04d}；关键短语：LAKALA-CACHE-PROBE-STABLE-PREFIX。\n"
    )
    parts: list[str] = []
    current_tokens = 0
    index = 1
    while current_tokens < target_tokens and index <= 2000:
        parts.append(block.format(index=index))
        index += 1
        current_tokens = estimate_tokens("".join(parts))
    return "".join(parts)


async def run_cache_behavior_probe(adapter: BaseAdapter, config: ModelConfig) -> MetricResult:
    target_tokens = _cache_probe_target_tokens(config)
    stable_prefix = _build_cache_probe_prefix(target_tokens)
    estimated_prefix_tokens = estimate_tokens(stable_prefix)
    suffix_a = "请用一句话回答：缓存探测第一轮的目的是什么？"
    suffix_b = "请用一句话回答：如果缓存命中，通常哪些观测值会发生变化？"
    prompts = [
        ("warmup_same_prompt", suffix_a),
        ("repeat_same_prompt", suffix_a),
        ("repeat_same_prefix_variant_suffix", suffix_b),
    ]

    rounds: list[dict[str, Any]] = []
    usage_field_paths: set[str] = set()
    cached_token_values: list[int] = []
    cache_hit_count = 0
    successful_count = 0

    for label, suffix in prompts:
        prompt = f"{stable_prefix}\n\n最后问题：{suffix}"
        response = await adapter.complete(AdapterRequest(prompt=prompt, max_tokens=64, temperature=0))
        cache_usage = _extract_cache_usage(response.usage)
        usage_field_paths.update(cache_usage["field_paths"])
        cached_tokens = cache_usage["cached_tokens"]
        cache_read_tokens = cache_usage["cache_read_tokens"]
        cache_hit = cache_usage["cache_hit"]
        if cached_tokens is not None:
            cached_token_values.append(cached_tokens)
        if (cache_hit is True) or (cache_read_tokens is not None and cache_read_tokens > 0):
            cache_hit_count += 1
        if response.ok:
            successful_count += 1
        rounds.append({
            "round": label,
            "http_status": response.http_status,
            "ok": response.ok,
            "latency_ms": response.latency_ms,
            "usage_prompt_tokens": _usage_prompt(response.usage),
            "usage_completion_tokens": _usage_completion(response.usage),
            "cached_tokens": cached_tokens,
            "cache_creation_tokens": cache_usage["cache_creation_tokens"],
            "cache_read_tokens": cache_read_tokens,
            "cache_hit": cache_hit,
            "usage_field_paths": cache_usage["field_paths"],
            "finish_reason": response.finish_reason,
            "error": response.error,
        })

    latencies = [r.get("latency_ms") for r in rounds]
    latency_baseline = latencies[0] if latencies and isinstance(latencies[0], (int, float)) else None
    repeated_latencies = [value for value in latencies[1:] if isinstance(value, (int, float))]
    repeated_avg = round(sum(repeated_latencies) / len(repeated_latencies), 3) if repeated_latencies else None
    latency_reduction_ms = None
    latency_reduction_ratio = None
    if latency_baseline is not None and repeated_avg is not None:
        latency_reduction_ms = round(latency_baseline - repeated_avg, 3)
        if latency_baseline > 0:
            latency_reduction_ratio = round(latency_reduction_ms / latency_baseline, 4)

    observations = {
        "request_count": len(prompts),
        "successful_count": successful_count,
        "stable_prefix_estimated_tokens": estimated_prefix_tokens,
        "target_prefix_tokens": target_tokens,
        "cache_signal_present": bool(usage_field_paths),
        "usage_field_paths_detected": sorted(usage_field_paths),
        "max_cached_tokens": max(cached_token_values) if cached_token_values else None,
        "cache_hit_count": cache_hit_count,
        "latency_baseline_ms": latency_baseline,
        "repeated_latency_avg_ms": repeated_avg,
        "latency_reduction_ms": latency_reduction_ms,
        "latency_reduction_ratio": latency_reduction_ratio,
        "rounds": rounds,
    }
    failed_rounds = [r for r in rounds if not r.get("ok")]
    if failed_rounds:
        return errored(
            "cache_behavior",
            "缓存能力探测请求存在失败轮次",
            observations,
            [{"code": "cache_probe_request_failed", "message": "至少一轮缓存探测请求失败", "failed_rounds": failed_rounds[:3]}],
        )
    return completed("cache_behavior", "缓存能力观测完成", observations)


async def run_connectivity_probe(adapter: BaseAdapter) -> MetricResult:
    prompt = "请用一句话说明大模型 API 验证服务的作用。"
    response = await adapter.complete(AdapterRequest(prompt=prompt))
    observations = {
        "http_status": response.http_status,
        "latency_ms": response.latency_ms,
        "response_json_parseable": response.raw is not None,
        "content_present": bool(response.content),
        "content_excerpt": response.content[:300],
        "finish_reason": response.finish_reason,
        "usage_present": response.usage is not None,
    }
    if not response.ok:
        return errored("connectivity", "连通性探测失败", observations, [_error_from_response(response, "连通性探测失败")])
    return completed("connectivity", "连通性探测完成", observations)


async def run_usage_probe(adapter: BaseAdapter) -> MetricResult:
    prompt = "请用三句话解释什么是 API 网关。"
    response = await adapter.complete(AdapterRequest(prompt=prompt))
    prompt_tokens = _usage_prompt(response.usage)
    completion_tokens = _usage_completion(response.usage)
    estimated_prompt = estimate_tokens(prompt)
    estimated_completion = estimate_tokens(response.content)
    token_error_ratio = None
    if completion_tokens:
        token_error_ratio = round(abs(completion_tokens - estimated_completion) / max(completion_tokens, 1), 4)
    observations = {
        "usage_present": response.usage is not None,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": _usage_total(response.usage),
        "estimated_prompt_tokens": estimated_prompt,
        "estimated_completion_tokens": estimated_completion,
        "prompt_token_delta": None if prompt_tokens is None else prompt_tokens - estimated_prompt,
        "completion_token_delta": None if completion_tokens is None else completion_tokens - estimated_completion,
        "token_error_ratio": token_error_ratio,
        "estimator": ESTIMATOR_NAME,
    }
    if response.usage is None:
        return errored("token_usage_accuracy", "响应中缺少 usage 字段", observations, [_error_from_response(response, "响应中缺少 usage 字段")])
    return completed("token_usage_accuracy", "Token 用量观测完成", observations)


async def run_stream_probe(adapter: BaseAdapter) -> tuple[MetricResult, MetricResult]:
    prompt = "请用中文分 5 点简要说明：为什么大模型 API 上线前需要做工程验证。"
    response = await adapter.stream(AdapterRequest(prompt=prompt, stream=True))
    parse_error_count = sum(1 for chunk in response.chunks if chunk.parse_error)
    done_present = any(chunk.done for chunk in response.chunks)
    stream_duration = None
    if response.ttft_ms is not None and response.end_to_end_latency_ms is not None:
        stream_duration = round(response.end_to_end_latency_ms - response.ttft_ms, 3)
    estimated_output = estimate_tokens(response.content)
    tps = None
    if stream_duration and stream_duration > 0:
        tps = round(estimated_output / (stream_duration / 1000), 3)
    latency_obs = {
        "ttft_ms": response.ttft_ms,
        "end_to_end_latency_ms": response.end_to_end_latency_ms,
        "stream_duration_ms": stream_duration,
        "output_char_count": len(response.content),
        "estimated_output_tokens": estimated_output,
        "tps_estimated": tps,
        "stream_event_count": len(response.chunks),
        "first_content_at": response.ttft_ms,
        "finished_at": response.end_to_end_latency_ms,
    }
    spec_obs = {
        "sse_parseable": parse_error_count == 0 and bool(response.chunks),
        "data_line_count": len(response.chunks),
        "event_count": len(response.chunks),
        "parse_error_count": parse_error_count,
        "done_event_present": done_present,
        "finish_reason": response.finish_reason,
        "finish_reason_present": response.finish_reason is not None,
        "stream_usage_present": response.usage is not None,
        "raw_event_excerpt": response.raw_event_excerpt,
    }
    if not response.ok:
        error = response.error or {"code": "stream_error", "message": "流式请求失败"}
        return (
            errored("latency_breakdown", "流式延迟探测失败", latency_obs, [error]),
            errored("stream_spec", "流式规范性探测失败", spec_obs, [error]),
        )
    return (
        completed("latency_breakdown", "流式延迟观测完成", latency_obs),
        completed("stream_spec", "流式格式观测完成", spec_obs),
    )


async def run_output_length_probe(adapter: BaseAdapter, config: ModelConfig) -> MetricResult:
    max_tokens = config.declared_max_output_tokens or 1024
    used_default = config.declared_max_output_tokens is None
    prompt = "请生成一篇结构化中文说明文，主题是“大模型 API 网关上线前验证”，尽量详细展开，不要提前结束。"
    response = await adapter.complete(AdapterRequest(prompt=prompt, max_tokens=max_tokens))
    observations = {
        "requested_max_tokens": max_tokens,
        "used_default_max_tokens": used_default,
        "output_char_count": len(response.content),
        "estimated_output_tokens": estimate_tokens(response.content),
        "finish_reason": response.finish_reason,
        "usage_completion_tokens": _usage_completion(response.usage),
        "content_excerpt": response.content[:500],
    }
    if not response.ok:
        return errored("output_length", "输出长度探测失败", observations, [_error_from_response(response, "output probe failed")])
    return completed("output_length", "输出长度观测完成", observations)

def _context_points(declared: int) -> list[int]:
    base_points = [4096, 8192, 16384, 32768, 65536, 131072, 262144, 524288]
    points = [point for point in base_points if point <= declared]
    if declared > 524288:
        points.extend([int(declared * 0.75), int(declared * 0.9), declared])
    elif declared not in points:
        points.append(declared)
    result: list[int] = []
    for point in sorted(points):
        if point >= 1 and point not in result:
            result.append(point)
    return result


_CONTEXT_NEEDLE_CODE = "ZXQ-7F3A9C-END"
_CONTEXT_RESPONSE_MAX_TOKENS = 256
_HARD_CONTEXT_HTTP_STATUSES = {400, 413, 422}


def _normalized_marker_text(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", value).upper()


def _contains_context_marker(content: str, marker: str) -> bool:
    normalized_marker = _normalized_marker_text(marker)
    return bool(normalized_marker and normalized_marker in _normalized_marker_text(content))


def _context_block(index: int) -> str:
    return (
        f"BEGIN_CONTEXT_BLOCK {index:06d}\n"
        f"主题：模型网关上线前验证记录 {index:06d}。\n"
        "要点：连通性、延迟拆解、上下文长度、输出长度、并发承载、限流行为、"
        "错误处理、Token 用量观测与流式规范性。\n"
        f"备注：本块只是干扰资料，不包含目标 NEEDLE_CODE；普通编号 CTX-{index:06d} 不等于答案。\n"
        f"END_CONTEXT_BLOCK {index:06d}\n"
    )


def _build_context_prompt(target_approx_tokens: int, marker: str) -> str:
    intro = (
        "你正在读取一份很长的模型网关验证资料。资料由多个 BEGIN_CONTEXT_BLOCK / "
        "END_CONTEXT_BLOCK 组成，其中只有一个块包含 NEEDLE_CODE。\n"
        "请不要总结资料，不要输出解释，最终只需要返回 NEEDLE_CODE 的值。\n"
    )
    needle = (
        "BEGIN_CONTEXT_BLOCK NEEDLE\n"
        "以下字段是本次上下文长度探测需要找回的唯一目标：\n"
        f"NEEDLE_CODE: {marker}\n"
        "如果后文出现其他 CTX 编号，请忽略它们。\n"
        "END_CONTEXT_BLOCK NEEDLE\n"
    )
    question = (
        "问题：上文唯一的 NEEDLE_CODE 的值是什么？\n"
        "回答要求：只输出 NEEDLE_CODE 的值，不要输出其他文字。"
    )
    scaffold_tokens = estimate_tokens(intro + needle + question)
    remaining_tokens = max(0, target_approx_tokens - scaffold_tokens)
    sample_tokens = max(1, estimate_tokens(_context_block(1)))
    total_blocks = max(1, (remaining_tokens + sample_tokens - 1) // sample_tokens)
    before_blocks = max(1, int(total_blocks * 0.65))
    after_blocks = max(0, total_blocks - before_blocks)
    before = "".join(_context_block(i) for i in range(1, before_blocks + 1))
    after = "".join(_context_block(100000 + i) for i in range(1, after_blocks + 1))
    return intro + before + needle + after + question


def _is_hard_context_http_error(response: AdapterResponse) -> bool:
    return (not response.ok) and response.http_status in _HARD_CONTEXT_HTTP_STATUSES


async def run_context_length_probe(adapter: BaseAdapter, config: ModelConfig) -> MetricResult:
    if config.declared_context_tokens is None:
        return skipped("context_length", "未配置 declared_context_tokens，跳过上下文长度探测")
    marker = _CONTEXT_NEEDLE_CODE
    test_points = _context_points(config.declared_context_tokens)
    point_results = []
    any_error = False
    observed_accepted_max_prompt_tokens: int | None = None
    observed_marker_found_max_prompt_tokens: int | None = None
    first_http_error_point: int | None = None
    first_marker_miss_point: int | None = None
    stopped_after_hard_error = False

    for point in test_points:
        prompt = _build_context_prompt(min(point, config.declared_context_tokens), marker)
        response = await adapter.complete(AdapterRequest(prompt=prompt, max_tokens=_CONTEXT_RESPONSE_MAX_TOKENS))
        accepted_by_api = response.ok
        marker_found = _contains_context_marker(response.content, marker)
        retrieval_ok = accepted_by_api and marker_found
        ok = retrieval_ok
        any_error = any_error or not ok

        if accepted_by_api:
            observed_accepted_max_prompt_tokens = point
            if not marker_found and first_marker_miss_point is None:
                first_marker_miss_point = point
        elif first_http_error_point is None:
            first_http_error_point = point

        if retrieval_ok:
            observed_marker_found_max_prompt_tokens = point

        point_results.append({
            "requested_approx_tokens": point,
            "prompt_char_length": len(prompt),
            "estimated_prompt_tokens": estimate_tokens(prompt),
            "ok": ok,
            "accepted_by_api": accepted_by_api,
            "retrieval_ok": retrieval_ok,
            "http_status": response.http_status,
            "latency_ms": response.latency_ms,
            "marker_found": marker_found,
            "finish_reason": response.finish_reason,
            "output_char_count": len(response.content),
            "content_excerpt": response.content[:500],
            "usage_prompt_tokens": _usage_prompt(response.usage),
            "usage_completion_tokens": _usage_completion(response.usage),
            "usage_total_tokens": _usage_total(response.usage),
            "error": response.error,
        })

        if _is_hard_context_http_error(response):
            stopped_after_hard_error = True
            break

    observations = {
        "declared_context_tokens": config.declared_context_tokens,
        "test_points": test_points,
        "executed_test_points": [item["requested_approx_tokens"] for item in point_results],
        "marker": marker,
        "prompt_style": "structured_needle_in_haystack_v2",
        "response_max_tokens": _CONTEXT_RESPONSE_MAX_TOKENS,
        "observed_accepted_max_prompt_tokens": observed_accepted_max_prompt_tokens,
        "observed_marker_found_max_prompt_tokens": observed_marker_found_max_prompt_tokens,
        "first_http_error_point": first_http_error_point,
        "first_marker_miss_point": first_marker_miss_point,
        "stopped_after_hard_error": stopped_after_hard_error,
        "point_results": point_results,
    }
    if any_error:
        errors = []
        if first_http_error_point is not None:
            errors.append({"code": "context_acceptance_failed", "message": f"API 在约 {first_http_error_point} tokens 测试点开始拒绝请求"})
        if first_marker_miss_point is not None:
            errors.append({"code": "context_retrieval_failed", "message": f"模型在约 {first_marker_miss_point} tokens 测试点开始未找回标记"})
        if not errors:
            errors.append({"code": "context_point_failed", "message": "至少一个上下文测试点未通过"})
        return errored("context_length", "上下文长度观测发现未通过点（API 接收与标记找回已分开记录）", observations, errors)
    return completed("context_length", "上下文长度观测完成", observations)


async def run_error_handling_probe(config: ModelConfig, adapter_factory: AdapterFactory) -> MetricResult:
    cases = [
        ("invalid_api_key", config.model_copy(update={"api_key": "invalid-api-key"}), AdapterRequest(prompt="hello")),
        ("invalid_model", config.model_copy(update={"model": "invalid-model-for-benchmark"}), AdapterRequest(prompt="hello")),
        ("empty_input", config, AdapterRequest(prompt="")),
        ("invalid_parameter", config, AdapterRequest(prompt="hello", extra_body={"temperature": -999})),
        ("context_overflow", config, AdapterRequest(prompt="溢" * max((config.declared_context_tokens or 8192) * 2, 20000), max_tokens=16)),
    ]
    observations = {"cases": []}
    executed = 0
    for case_id, case_config, request in cases:
        adapter = adapter_factory(case_config)
        response = await adapter.complete(request)
        executed += 1
        raw_excerpt = ""
        if response.raw:
            raw_excerpt = str(response.raw)[:500]
        elif response.error:
            raw_excerpt = str(response.error)[:500]
        observations["cases"].append({
            "case_id": case_id,
            "http_status": response.http_status,
            "latency_ms": response.latency_ms,
            "error_shape_present": response.error is not None,
            "error_code": (response.error or {}).get("code"),
            "error_message_excerpt": str((response.error or {}).get("message", ""))[:300],
            "raw_excerpt": raw_excerpt,
        })
    if executed == 0:
        return errored("error_handling", "错误处理探测未能执行", observations, [{"code": "no_cases_executed", "message": "没有执行任何错误场景"}])
    return completed("error_handling", "错误处理观测完成", observations)


async def run_concurrency_probe(adapter: BaseAdapter, config: ModelConfig) -> tuple[MetricResult, MetricResult]:
    levels = config.concurrency_levels or [1, 5, 10, 20]
    per_level = []
    total_requests = success_count = error_count = rate_limited_count = 0
    rate_limited_statuses: set[int] = set()
    first_rate_limit_level = None
    examples = []

    async def one_request(index: int):
        return await adapter.complete(AdapterRequest(prompt=f"请简短回答：并发测试请求 {index}"))

    for level in levels:
        responses = await asyncio.gather(*(one_request(i) for i in range(level)), return_exceptions=True)
        level_success = level_error = level_rate_limited = 0
        latencies = []
        for response in responses:
            total_requests += 1
            if isinstance(response, Exception):
                level_error += 1
                error_count += 1
                examples.append({"level": level, "error": str(response)[:300]})
                continue
            if response.latency_ms is not None:
                latencies.append(response.latency_ms)
            if response.http_status == 429:
                level_rate_limited += 1
                rate_limited_count += 1
                rate_limited_statuses.add(429)
                if first_rate_limit_level is None:
                    first_rate_limit_level = level
                if len(examples) < 5:
                    examples.append({"level": level, "http_status": response.http_status, "error": response.error})
            if response.ok:
                level_success += 1
                success_count += 1
            else:
                level_error += 1
                error_count += 1
        per_level.append({
            "level": level,
            "requests": level,
            "success_count": level_success,
            "error_count": level_error,
            "rate_limited_count": level_rate_limited,
            "latency_ms_min": min(latencies) if latencies else None,
            "latency_ms_max": max(latencies) if latencies else None,
            "latency_ms_avg": round(sum(latencies) / len(latencies), 3) if latencies else None,
        })

    concurrency_obs = {"levels": levels, "per_level": per_level, "total_requests": total_requests, "success_count": success_count, "error_count": error_count, "rate_limited_count": rate_limited_count}
    rate_obs = {"rate_limited_count": rate_limited_count, "rate_limited_http_statuses": sorted(rate_limited_statuses), "first_rate_limit_observed_at_level": first_rate_limit_level, "examples": examples[:5]}
    concurrency_result = completed("concurrency", "并发承载观测完成", concurrency_obs) if success_count > 0 else errored("concurrency", "所有并发请求均失败", concurrency_obs, [{"code": "all_concurrency_failed", "message": "没有并发请求成功"}])
    rate_result = completed("rate_limit", "限流行为观测完成", rate_obs)
    return concurrency_result, rate_result
