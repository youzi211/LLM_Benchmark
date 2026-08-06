from app.core.models import MetricResult, TaskResult, utc_now
from app.reports.facts import (
    build_report_fact_pack,
    metric_core_observation_text,
    suggested_focus_text,
)


def _make_task_result(results: list[MetricResult]) -> TaskResult:
    started = utc_now()
    return TaskResult(
        task_id="task_fact_pack",
        status="completed",
        model_id="minimax-m3-ark-real",
        model_config_name="MiniMax-M3 火山方舟兼容接口",
        upstream_model_name="minimax-m3",
        protocol="chat_completions",
        plan_id="gateway_baseline_v1",
        metric_ids=[r.metric_id for r in results],
        started_at=started,
        finished_at=started,
        duration_ms=127.5,
        results=results,
    )


def test_report_fact_pack_counts_status_and_extracts_context_key_facts():
    result = _make_task_result(
        [
            MetricResult(
                metric_id="connectivity",
                metric_name="连通性",
                status="completed",
                summary="连通性探测完成",
                observations={
                    "http_status": 200,
                    "latency_ms": 123.4,
                    "content_present": True,
                },
            ),
            MetricResult(
                metric_id="context_length",
                metric_name="上下文长度",
                status="error",
                summary="上下文存在未通过点",
                observations={
                    "declared_context_tokens": 1048576,
                    "observed_accepted_max_prompt_tokens": 943718,
                    "observed_marker_found_max_prompt_tokens": 943718,
                    "first_http_error_point": 1048576,
                    "first_marker_miss_point": None,
                    "point_results": [
                        {
                            "requested_approx_tokens": 943718,
                            "accepted_by_api": True,
                            "retrieval_ok": True,
                            "http_status": 200,
                            "usage_prompt_tokens": 817455,
                            "content_excerpt": "sensitive long content",
                            "full_prompt": "secret prompt",
                        },
                        {
                            "requested_approx_tokens": 1048576,
                            "accepted_by_api": False,
                            "retrieval_ok": False,
                            "http_status": 429,
                            "error": {
                                "code": "AccountQuotaExceeded",
                                "message": "quota",
                            },
                            "content_excerpt": "leaked",
                        },
                    ],
                },
                errors=[
                    {"code": "context_acceptance_failed", "message": "1024K failed"}
                ],
            ),
        ]
    )

    facts = build_report_fact_pack(result)

    assert facts.status_counts.total == 2
    assert facts.status_counts.completed == 1
    assert facts.status_counts.error == 1
    context = next(
        item for item in facts.metric_facts if item.metric_id == "context_length"
    )
    assert context.key_facts["observed_accepted_max_prompt_tokens"] == 943718
    excerpt = context.important_raw_excerpt[0]
    assert excerpt.label == "context_point_results"
    assert len(excerpt.data) == 2
    for point in excerpt.data:
        assert "content_excerpt" not in point
        assert "full_prompt" not in point
    assert excerpt.data[1]["error"]["code"] == "AccountQuotaExceeded"


def test_metric_core_observation_text_returns_chinese_summary():
    item = MetricResult(
        metric_id="stream_spec",
        metric_name="流式规范性",
        status="completed",
        summary="流式规范观测完成",
        observations={
            "http_status": 200,
            "ttft_ms": 653.2,
            "done_present": True,
            "finish_reason_present": True,
            "stream_usage_present": False,
        },
    )

    text = metric_core_observation_text(item)

    assert "HTTP 200" in text
    assert "TTFT 653.2 ms" in text
    assert "[DONE]：是" in text


def test_suggested_focus_text_for_all_statuses():
    completed = MetricResult(
        metric_id="m",
        status="completed",
        summary="ok",
        observations={},
    )
    error = MetricResult(
        metric_id="m",
        status="error",
        summary="bad",
        observations={},
    )
    skipped = MetricResult(
        metric_id="m",
        status="skipped",
        summary="skip",
        observations={},
    )

    assert "无回归" in suggested_focus_text(completed)
    assert "排查异常" in suggested_focus_text(error)
    assert "是否仍需" in suggested_focus_text(skipped)


def test_core_observation_falls_back_to_summary_when_observations_empty():
    item = MetricResult(
        metric_id="latency",
        metric_name="延迟",
        status="completed",
        summary="延迟观测完成",
        observations={},
    )

    text = metric_core_observation_text(item)

    assert text == "延迟观测完成"


def test_generic_core_observation_separates_finish_reason_and_presence():
    item = MetricResult(
        metric_id="token_usage_accuracy",
        metric_name="Token 用量准确度",
        status="completed",
        summary="ok",
        observations={
            "http_status": 200,
            "finish_reason": "stop",
            "finish_reason_present": True,
        },
    )

    text = metric_core_observation_text(item)

    assert "finish_reason：stop" in text
    assert "finish_reason_present：是" in text


def test_non_dict_errors_are_ignored_when_extracting_error_codes():
    item = MetricResult(
        metric_id="connectivity",
        metric_name="连通性",
        status="error",
        summary="失败",
        observations={"http_status": 500},
        errors=[{"code": "BadGateway"}],
    )
    item.errors = [1, {"code": "BadGateway"}, "timeout"]

    text = metric_core_observation_text(item)
    assert "BadGateway" in text
    assert "timeout" not in text

    facts = build_report_fact_pack(_make_task_result([item]))
    metric_fact = facts.metric_facts[0]
    assert metric_fact.key_facts["error_codes"] == ["BadGateway"]
    error_excerpt = next(e for e in metric_fact.important_raw_excerpt if e.label == "errors")
    assert error_excerpt.data == [{"code": "BadGateway", "message": None}]


def test_generic_metric_keeps_only_whitelist_fields():
    item = MetricResult(
        metric_id="concurrency",
        metric_name="并发",
        status="completed",
        summary="ok",
        observations={
            "http_status": 200,
            "latency_ms": 55.5,
            "content_excerpt": "should not appear",
            "full_prompt": "secret",
            "finish_reason": "stop",
            "finish_reason_present": True,
            "usage": {"prompt_tokens": 10},
            "concurrency_level": 20,
        },
    )

    facts = build_report_fact_pack(_make_task_result([item]))
    metric_fact = facts.metric_facts[0]

    assert "content_excerpt" not in metric_fact.key_facts
    assert "full_prompt" not in metric_fact.key_facts
    assert metric_fact.key_facts["finish_reason"] == "stop"
    assert metric_fact.key_facts["finish_reason_present"] is True
    assert metric_fact.key_facts["usage"] == {"prompt_tokens": 10}
    assert metric_fact.key_facts["concurrency_level"] == 20

    raw = next(e for e in metric_fact.important_raw_excerpt if e.label == "observations")
    assert "content_excerpt" not in raw.data
    assert "full_prompt" not in raw.data
    assert raw.data["finish_reason_present"] is True
    assert "finish_reason" not in raw.data


def test_context_length_raw_excerpt_excludes_sensitive_fields():
    item = MetricResult(
        metric_id="context_length",
        metric_name="上下文长度",
        status="error",
        summary="上下文存在未通过点",
        observations={
            "point_results": [
                {
                    "requested_approx_tokens": 100,
                    "accepted_by_api": True,
                    "retrieval_ok": True,
                    "http_status": 200,
                    "usage_prompt_tokens": 50,
                    "content_excerpt": "sensitive content",
                    "full_prompt": "secret prompt",
                    "raw_response": "huge response body",
                }
            ]
        },
    )

    facts = build_report_fact_pack(_make_task_result([item]))
    point = facts.metric_facts[0].important_raw_excerpt[0].data[0]

    assert "content_excerpt" not in point
    assert "full_prompt" not in point
    assert "raw_response" not in point


def test_context_length_error_message_is_truncated():
    long_message = "x" * 500
    item = MetricResult(
        metric_id="context_length",
        metric_name="上下文长度",
        status="error",
        summary="fail",
        observations={
            "point_results": [
                {
                    "requested_approx_tokens": 100,
                    "accepted_by_api": False,
                    "retrieval_ok": False,
                    "http_status": 400,
                    "usage_prompt_tokens": 50,
                    "error": {"code": "Err", "message": long_message},
                }
            ]
        },
    )

    facts = build_report_fact_pack(_make_task_result([item]))
    error = facts.metric_facts[0].important_raw_excerpt[0].data[0]["error"]

    assert error["code"] == "Err"
    assert len(error["message"]) < len(long_message)
    assert error["message"].endswith("...")


def test_build_fact_pack_handles_empty_results():
    facts = build_report_fact_pack(_make_task_result([]))

    assert facts.status_counts.total == 0
    assert facts.metric_facts == []


def test_build_fact_pack_handles_all_skipped():
    result = _make_task_result(
        [
            MetricResult(
                metric_id="m1",
                status="skipped",
                summary="skipped 1",
                observations={},
            ),
            MetricResult(
                metric_id="m2",
                status="skipped",
                summary="skipped 2",
                observations={},
            ),
        ]
    )

    facts = build_report_fact_pack(result)

    assert facts.status_counts.total == 2
    assert facts.status_counts.skipped == 2
    assert facts.status_counts.completed == 0
    assert all(
        mf.suggested_focus == "确认该指标是否仍需评测。"
        for mf in facts.metric_facts
    )



def test_cache_behavior_fact_pack_highlights_cache_observations():
    item = MetricResult(
        metric_id="cache_behavior",
        metric_name="缓存能力（Prompt Cache）",
        status="completed",
        summary="缓存能力观测完成",
        observations={
            "request_count": 3,
            "successful_count": 3,
            "cache_signal_present": True,
            "usage_field_paths_detected": ["prompt_tokens_details.cached_tokens"],
            "max_cached_tokens": 1536,
            "cache_hit_count": 2,
            "latency_baseline_ms": 300,
            "repeated_latency_avg_ms": 120,
            "latency_reduction_ms": 180,
            "latency_reduction_ratio": 0.6,
            "rounds": [
                {
                    "round": "warmup_same_prompt",
                    "http_status": 200,
                    "ok": True,
                    "latency_ms": 300,
                    "cached_tokens": 0,
                    "cache_hit": False,
                },
                {
                    "round": "repeat_same_prompt",
                    "http_status": 200,
                    "ok": True,
                    "latency_ms": 120,
                    "cached_tokens": 1536,
                    "cache_hit": True,
                },
            ],
        },
    )

    text = metric_core_observation_text(item)
    facts = build_report_fact_pack(_make_task_result([item])).metric_facts[0]

    assert "缓存字段：是" in text
    assert "最大 cached tokens：1536" in text
    assert facts.key_facts["cache_signal_present"] is True
    assert facts.key_facts["cache_hit_count"] == 2
    assert facts.key_facts["latency_reduction_ratio"] == 0.6
    assert facts.important_raw_excerpt[0].label == "cache_rounds"
    assert facts.important_raw_excerpt[0].data[1]["cached_tokens"] == 1536
