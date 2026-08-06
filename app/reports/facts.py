from __future__ import annotations

from typing import Any

from app.core.models import MetricResult, TaskResult
from app.core.plans import format_metric_label
from app.reports.schemas import (
    ReportFactPack,
    ReportMetricFact,
    ReportRawExcerpt,
    ReportStatusCounts,
    ReportTaskFacts,
)


_MAX_CONTEXT_ERROR_MESSAGE_LEN = 200


def _metric_display_name(item: MetricResult) -> str:
    if item.metric_name:
        return item.metric_name
    return format_metric_label(item.metric_id)


def _bool_zh(value: Any) -> str:
    if value is True:
        return "是"
    if value is False:
        return "否"
    return "未知"


def _first_error_code(errors: list[Any]) -> str:
    for err in errors:
        if isinstance(err, dict):
            code = err.get("code")
            if code is not None:
                return str(code)
    return ""


def _compact_context_error(error: Any) -> Any:
    if not isinstance(error, dict):
        return error
    message = error.get("message")
    if isinstance(message, str) and len(message) > _MAX_CONTEXT_ERROR_MESSAGE_LEN:
        message = message[:_MAX_CONTEXT_ERROR_MESSAGE_LEN] + "..."
    compact: dict[str, Any] = {}
    code = error.get("code")
    if code is not None:
        compact["code"] = code
    if message is not None:
        compact["message"] = message
    return compact if compact else error


def build_report_fact_pack(result: TaskResult) -> ReportFactPack:
    task_facts = ReportTaskFacts(
        task_id=result.task_id,
        model_id=result.model_id,
        model_config_name=result.model_config_name,
        upstream_model_name=result.upstream_model_name,
        protocol=result.protocol,
        plan_id=result.plan_id,
        duration_ms=result.duration_ms,
    )

    counts = ReportStatusCounts()
    metric_facts: list[ReportMetricFact] = []
    for item in result.results:
        counts.total += 1
        if item.status == "completed":
            counts.completed += 1
        elif item.status == "error":
            counts.error += 1
        elif item.status == "skipped":
            counts.skipped += 1

        metric_facts.append(
            ReportMetricFact(
                metric_id=item.metric_id,
                metric_name=_metric_display_name(item),
                status=item.status,
                summary=item.summary,
                core_observation=metric_core_observation_text(item),
                suggested_focus=suggested_focus_text(item),
                key_facts=metric_key_facts(item),
                important_raw_excerpt=metric_raw_excerpts(item),
            )
        )

    return ReportFactPack(
        task=task_facts,
        status_counts=counts,
        metric_facts=metric_facts,
    )


def metric_key_facts(item: MetricResult) -> dict[str, Any]:
    facts: dict[str, Any] = {}
    obs = item.observations

    if item.metric_id == "context_length":
        for key in (
            "declared_context_tokens",
            "observed_accepted_max_prompt_tokens",
            "observed_marker_found_max_prompt_tokens",
            "first_http_error_point",
            "first_marker_miss_point",
            "stopped_after_hard_error",
        ):
            if key in obs:
                facts[key] = obs[key]
        return facts

    if item.metric_id == "cache_behavior":
        for key in (
            "request_count",
            "successful_count",
            "stable_prefix_estimated_tokens",
            "target_prefix_tokens",
            "cache_signal_present",
            "usage_field_paths_detected",
            "max_cached_tokens",
            "cache_hit_count",
            "latency_baseline_ms",
            "repeated_latency_avg_ms",
            "latency_reduction_ms",
            "latency_reduction_ratio",
        ):
            if key in obs:
                facts[key] = obs[key]
        return facts

    # Generic / stream_spec stable fields
    for key in (
        "http_status",
        "latency_ms",
        "ttft_ms",
        "content_present",
        "done_present",
        "finish_reason_present",
        "finish_reason",
        "stream_usage_present",
        "usage",
        "declared_context_tokens",
        "declared_max_output_tokens",
        "observed_max_output_tokens",
        "concurrency_level",
        "first_rate_limited_level",
    ):
        if key in obs:
            facts[key] = obs[key]

    if item.errors:
        error_codes = [
            str(e.get("code"))
            for e in item.errors
            if isinstance(e, dict) and e.get("code")
        ]
        if error_codes:
            facts["error_codes"] = error_codes

    return facts


_CONTEXT_POINT_KEYS = (
    "requested_approx_tokens",
    "accepted_by_api",
    "retrieval_ok",
    "http_status",
    "usage_prompt_tokens",
    "error",
)


def metric_raw_excerpts(item: MetricResult) -> list[ReportRawExcerpt]:
    excerpts: list[ReportRawExcerpt] = []
    obs = item.observations

    if item.metric_id == "context_length":
        point_results = obs.get("point_results")
        if isinstance(point_results, list):
            compact = []
            for point in point_results:
                if isinstance(point, dict):
                    compact_point = {
                        k: _compact_context_error(point.get(k))
                        if k == "error"
                        else point.get(k)
                        for k in _CONTEXT_POINT_KEYS
                    }
                    compact.append(compact_point)
                else:
                    compact.append(point)
            excerpts.append(ReportRawExcerpt(label="context_point_results", data=compact))
        return excerpts

    if item.metric_id == "cache_behavior":
        rounds = obs.get("rounds")
        if isinstance(rounds, list):
            compact = []
            for round_item in rounds:
                if isinstance(round_item, dict):
                    compact.append({
                        "round": round_item.get("round"),
                        "http_status": round_item.get("http_status"),
                        "ok": round_item.get("ok"),
                        "latency_ms": round_item.get("latency_ms"),
                        "usage_prompt_tokens": round_item.get("usage_prompt_tokens"),
                        "cached_tokens": round_item.get("cached_tokens"),
                        "cache_creation_tokens": round_item.get("cache_creation_tokens"),
                        "cache_read_tokens": round_item.get("cache_read_tokens"),
                        "cache_hit": round_item.get("cache_hit"),
                        "usage_field_paths": round_item.get("usage_field_paths"),
                        "error": _compact_context_error(round_item.get("error")),
                    })
                else:
                    compact.append(round_item)
            excerpts.append(ReportRawExcerpt(label="cache_rounds", data=compact))
        return excerpts

    # Bounded generic excerpt: selected stable observation fields only
    selected: dict[str, Any] = {}
    for key in (
        "http_status",
        "latency_ms",
        "ttft_ms",
        "content_present",
        "done_present",
        "finish_reason_present",
        "stream_usage_present",
        "usage",
    ):
        if key in obs:
            selected[key] = obs[key]
    if selected:
        excerpts.append(ReportRawExcerpt(label="observations", data=selected))

    if item.errors:
        error_excerpt = [
            {"code": err.get("code"), "message": err.get("message")}
            for err in item.errors[:3]
            if isinstance(err, dict)
        ]
        if error_excerpt:
            excerpts.append(ReportRawExcerpt(label="errors", data=error_excerpt))

    return excerpts


def metric_core_observation_text(item: MetricResult) -> str:
    obs = item.observations

    if item.metric_id == "stream_spec":
        return (
            f"HTTP {obs.get('http_status', '未知')}，"
            f"TTFT {obs.get('ttft_ms', '未知')} ms，"
            f"[DONE]：{_bool_zh(obs.get('done_present'))}，"
            f"finish_reason：{_bool_zh(obs.get('finish_reason_present'))}，"
            f"stream usage：{_bool_zh(obs.get('stream_usage_present'))}"
        )

    if item.metric_id == "context_length":
        declared = obs.get("declared_context_tokens")
        accepted = obs.get("observed_accepted_max_prompt_tokens")
        marker = obs.get("observed_marker_found_max_prompt_tokens")
        first_http_err = obs.get("first_http_error_point")
        first_marker_miss = obs.get("first_marker_miss_point")
        parts = []
        if declared is not None:
            parts.append(f"声明上下文 {declared} tokens")
        if accepted is not None:
            parts.append(f"API 实际接受最大 prompt {accepted} tokens")
        if marker is not None:
            parts.append(f"成功找回 marker 的最大 prompt {marker} tokens")
        if first_http_err is not None:
            parts.append(f"首次 HTTP 异常点 {first_http_err} tokens")
        if first_marker_miss is not None:
            parts.append(f"首次 marker 丢失点 {first_marker_miss} tokens")
        if not parts:
            parts.append(item.summary)
        return "；".join(parts) + "。"

    if item.metric_id == "cache_behavior":
        parts = [f"缓存字段：{_bool_zh(obs.get('cache_signal_present'))}"]
        if obs.get("max_cached_tokens") is not None:
            parts.append(f"最大 cached tokens：{obs['max_cached_tokens']}")
        if obs.get("cache_hit_count") is not None:
            parts.append(f"缓存命中轮次：{obs['cache_hit_count']}/{obs.get('request_count', '未知')}")
        baseline = obs.get("latency_baseline_ms")
        repeated_avg = obs.get("repeated_latency_avg_ms")
        if baseline is not None:
            parts.append(f"首轮延迟 {baseline} ms")
        if repeated_avg is not None:
            parts.append(f"重复轮平均延迟 {repeated_avg} ms")
        reduction_ratio = obs.get("latency_reduction_ratio")
        if isinstance(reduction_ratio, (int, float)):
            parts.append(f"延迟下降比例 {round(reduction_ratio * 100, 2)}%")
        return "，".join(parts) + "。"

    # Generic observation
    parts = []
    http_status = obs.get("http_status")
    if http_status is not None:
        parts.append(f"HTTP {http_status}")
    latency = obs.get("latency_ms")
    if latency is None:
        latency = obs.get("ttft_ms")
    if latency is not None:
        parts.append(f"延迟 {latency} ms")
    content = obs.get("content_present")
    if content is not None:
        parts.append(f"内容返回：{_bool_zh(content)}")
    if "finish_reason_present" in obs:
        parts.append(
            f"finish_reason_present：{_bool_zh(obs['finish_reason_present'])}"
        )
    if "finish_reason" in obs:
        parts.append(f"finish_reason：{obs['finish_reason']}")
    usage = obs.get("usage")
    if isinstance(usage, dict):
        parts.append(f"usage：{usage}")

    if item.status == "error" and item.errors:
        code = _first_error_code(item.errors)
        if code:
            parts.append(f"错误码：{code}")

    if not parts:
        return item.summary
    return "，".join(parts) + "。"


def suggested_focus_text(item: MetricResult) -> str:
    if item.status == "completed":
        return "复核核心观测，确保无回归。"
    if item.status == "error":
        return "优先排查异常原因并复测。"
    if item.status == "skipped":
        return "确认该指标是否仍需评测。"
    return "关注该指标结果。"
