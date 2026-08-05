from pathlib import Path

from app.core.models import MetricResult, TaskResult, utc_now
from app.reports.markdown import write_markdown_report


def test_markdown_report_uses_chinese_friendly_metric_labels(tmp_path):
    started = utc_now()
    result = TaskResult(
        task_id="task_cn_report",
        status="completed",
        model_id="demo-model",
        plan_id="gateway_baseline_v1",
        metric_ids=["connectivity", "latency_breakdown"],
        started_at=started,
        finished_at=started,
        duration_ms=12.3,
        results=[
            MetricResult(
                metric_id="connectivity",
                status="completed",
                summary="连通性探测完成",
                observations={"http_status": 200},
            ),
            MetricResult(
                metric_id="latency_breakdown",
                status="error",
                summary="流式延迟采集失败",
                observations={},
                errors=[{"code": "stream_request_failed", "message": "流式请求失败"}],
            ),
        ],
    )

    report_path = write_markdown_report(result, tmp_path)
    text = Path(report_path).read_text(encoding="utf-8")

    assert "# 大模型 API 评测报告 - task_cn_report" in text
    assert "| 指标 | 状态 | 摘要 |" in text
    assert "| 连通性（connectivity） | 已完成（completed） | 连通性探测完成 |" in text
    assert "| 延迟拆解（latency_breakdown） | 异常（error） | 流式延迟采集失败 |" in text
    assert "## 连通性（connectivity）" in text
    assert "### 观测数据" in text
    assert "### 错误信息" in text
    assert "| `connectivity` | `completed` |" not in text


def test_markdown_report_separates_config_id_from_upstream_model_name(tmp_path):
    started = utc_now()
    result = TaskResult(
        task_id="task_model_names",
        status="completed",
        model_id="glm-5-2-fp8-real",
        model_config_name="GLM 真实网关配置",
        upstream_model_name="GLM-5.2-FP8",
        protocol="chat_completions",
        plan_id="gateway_baseline_v1",
        metric_ids=[],
        started_at=started,
        finished_at=started,
        duration_ms=1.0,
        results=[],
    )

    report_path = write_markdown_report(result, tmp_path)
    text = Path(report_path).read_text(encoding="utf-8")

    assert "- 模型配置 ID：`glm-5-2-fp8-real`" in text
    assert "- 模型配置名称：`GLM 真实网关配置`" in text
    assert "- API 模型名称（model）：`GLM-5.2-FP8`" in text
    assert "- 协议：`chat_completions`" in text
    assert "- Model ID:" not in text



from app.reports.markdown import redact_text


def test_redact_text_does_not_redact_ordinary_identifiers():
    assert redact_text("minimax-m3-ark-real") == "minimax-m3-ark-real"
    assert redact_text("task-risk-management") == "task-risk-management"
    assert redact_text("park-secret123") == "park-secret123"
    assert redact_text("ask-secret123") == "ask-secret123"


def test_redact_text_redacts_isolated_sk_ark_tokens():
    assert redact_text("sk-live-abc123") == "sk-***"
    assert redact_text("ark-api-xyz789") == "ark-***"
    assert redact_text('"sk-live-abc123"') == '"sk-***"'
    assert (
        redact_text("Connection failed: sk-live-abc123 and ark-api-xyz789")
        == "Connection failed: sk-*** and ark-***"
    )
