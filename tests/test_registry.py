def test_gateway_plan_contains_expected_metrics():
    from app.core.registry import resolve_metric_ids

    assert resolve_metric_ids("gateway_baseline_v1", None) == [
        "connectivity",
        "latency_breakdown",
        "context_length",
        "output_length",
        "concurrency",
        "rate_limit",
        "error_handling",
        "token_usage_accuracy",
        "stream_spec",
    ]


def test_invalid_metric_is_rejected():
    from app.core.registry import resolve_metric_ids

    try:
        resolve_metric_ids("gateway_baseline_v1", ["not_exist"])
    except ValueError as exc:
        assert str(exc) == "invalid_metric:not_exist"
    else:
        raise AssertionError("expected ValueError")
from app.core.registry import get_metric, list_metrics


def test_metric_catalog_is_chinese_friendly_while_ids_remain_stable():
    metrics = {metric.id: metric for metric in list_metrics()}

    assert metrics["connectivity"].name == "连通性"
    assert metrics["latency_breakdown"].name == "延迟拆解"
    assert metrics["stream_spec"].name == "流式规范性"
    assert "检查" in metrics["connectivity"].description
    assert "TTFT" in metrics["latency_breakdown"].description
    assert "SSE" in metrics["stream_spec"].description
    assert "gateway_baseline_v1 metric" not in metrics["connectivity"].description

    assert get_metric("token_usage_accuracy").name == "Token 用量观测（Usage）"
