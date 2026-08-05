from app.core.models import MetricResult, TaskResult, utc_now
from app.reports.facts import build_report_fact_pack, metric_core_observation_text


def test_report_fact_pack_counts_status_and_extracts_context_key_facts():
    started = utc_now()
    result = TaskResult(
        task_id="task_fact_pack",
        status="completed",
        model_id="minimax-m3-ark-real",
        model_config_name="MiniMax-M3 火山方舟兼容接口",
        upstream_model_name="minimax-m3",
        protocol="chat_completions",
        plan_id="gateway_baseline_v1",
        metric_ids=["connectivity", "context_length"],
        started_at=started,
        finished_at=started,
        duration_ms=127.5,
        results=[
            MetricResult(metric_id="connectivity", metric_name="连通性", status="completed", summary="连通性探测完成", observations={"http_status": 200, "latency_ms": 123.4, "content_present": True}),
            MetricResult(metric_id="context_length", metric_name="上下文长度", status="error", summary="上下文存在未通过点", observations={"declared_context_tokens":1048576,"observed_accepted_max_prompt_tokens":943718,"observed_marker_found_max_prompt_tokens":943718,"first_http_error_point":1048576,"first_marker_miss_point":None,"point_results":[{"requested_approx_tokens":943718,"accepted_by_api":True,"retrieval_ok":True,"http_status":200,"usage_prompt_tokens":817455},{"requested_approx_tokens":1048576,"accepted_by_api":False,"retrieval_ok":False,"http_status":429,"error":{"code":"AccountQuotaExceeded","message":"quota"}}]}, errors=[{"code":"context_acceptance_failed","message":"1024K failed"}]),
        ],
    )

    facts = build_report_fact_pack(result)

    assert facts.status_counts.total == 2
    assert facts.status_counts.completed == 1
    assert facts.status_counts.error == 1
    context = next(item for item in facts.metric_facts if item.metric_id == "context_length")
    assert context.key_facts["observed_accepted_max_prompt_tokens"] == 943718
    assert context.important_raw_excerpt[0].label == "context_point_results"
    assert len(context.important_raw_excerpt[0].data) == 2


def test_metric_core_observation_text_returns_chinese_summary():
    item = MetricResult(metric_id="stream_spec", metric_name="流式规范性", status="completed", summary="流式规范观测完成", observations={"http_status": 200, "ttft_ms": 653.2, "done_present": True, "finish_reason_present": True, "stream_usage_present": False})

    text = metric_core_observation_text(item)

    assert "HTTP 200" in text
    assert "TTFT 653.2 ms" in text
    assert "[DONE]：是" in text
