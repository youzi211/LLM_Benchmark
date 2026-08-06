def test_gateway_acceptance_plan_contains_expected_smoke_metrics():
    from app.core.registry import resolve_metric_ids

    expected = [
        "connectivity",
        "latency_breakdown",
        "context_length",
        "output_length",
        "error_handling",
        "token_usage_accuracy",
        "cache_behavior",
        "stream_spec",
    ]
    assert resolve_metric_ids("gateway_acceptance_v1", None) == expected
    # gateway_baseline_v1 is kept as a compatibility alias with the reduced semantics.
    assert resolve_metric_ids("gateway_baseline_v1", None) == expected


def test_legacy_perf_smoke_metrics_remain_explicitly_runnable_but_not_default():
    from app.core.registry import list_metrics, resolve_metric_ids

    assert resolve_metric_ids("gateway_acceptance_v1", ["concurrency", "rate_limit"]) == ["concurrency", "rate_limit"]
    by_id = {metric.id: metric for metric in list_metrics()}
    assert by_id["concurrency"].default_in_gateway_baseline_v1 is False
    assert by_id["rate_limit"].default_in_gateway_baseline_v1 is False
    assert by_id["concurrency"].priority == "P2"
    assert by_id["rate_limit"].priority == "P2"


def test_run_task_defaults_to_gateway_acceptance_plan():
    from app.core.models import RunTaskRequest

    request = RunTaskRequest(model_id="demo-chat")

    assert request.plan_id == "gateway_acceptance_v1"
