from pathlib import Path

from app.core.models import MetricResult, TaskResult, utc_now
from app.reports.facts import build_report_fact_pack
from app.reports.markdown import redact_text, write_markdown_report
from app.reports.schemas import ReportAnalysis, ReportAnalysisMetricNote


def _completed_analysis() -> ReportAnalysis:
    return ReportAnalysis(
        analysis_status="completed",
        analysis_model_id="report-analyzer",
        one_sentence_summary="本次评测基础链路可用。",
        overall_assessment="指标整体可读，异常项需人工复核。",
        key_findings=["连通性完成"],
        risks=["需要复核上下文指标"],
        recommended_next_steps=["查看指标明细"],
    )


def test_markdown_report_uses_dashboard_and_detail_layout(tmp_path):
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
    facts = build_report_fact_pack(result)
    analysis = _completed_analysis()

    report_path = write_markdown_report(result, tmp_path, facts=facts, analysis=analysis)
    text = Path(report_path).read_text(encoding="utf-8")

    assert "# 大模型 API 评测报告 - task_cn_report" in text
    assert "## 0. LLM 分析摘要" in text
    assert "## 1. 任务概览" in text
    assert "## 2. 指标仪表盘" in text
    assert "| 指标总数 | 已完成 | 异常 | 已跳过 |" in text
    assert "## 3. 指标总表" in text
    assert "| 指标 | 状态 | 核心观测 | 建议关注 |" in text
    assert "## 4. 指标明细" in text
    assert "## 5. 附录" in text
    assert "- 分析模型 ID：`report-analyzer`" in text
    assert "| 连通性（connectivity） | 已完成（completed） |" in text
    assert "| 延迟拆解（latency_breakdown） | 异常（error） |" in text
    assert "### 观测数据" in text
    assert "### 错误信息" in text


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
    facts = build_report_fact_pack(result)
    analysis = _completed_analysis()

    report_path = write_markdown_report(result, tmp_path, facts=facts, analysis=analysis)
    text = Path(report_path).read_text(encoding="utf-8")

    assert "- 模型配置 ID：`glm-5-2-fp8-real`" in text
    assert "- 模型配置名称：`GLM 真实网关配置`" in text
    assert "- API 模型名称（model）：`GLM-5.2-FP8`" in text
    assert "- 协议：`chat_completions`" in text
    assert "- Model ID:" not in text


def test_markdown_report_escapes_table_cells(tmp_path):
    started = utc_now()
    result = TaskResult(
        task_id="task_table_escape",
        status="completed",
        model_id="demo-model",
        plan_id="gateway_baseline_v1",
        metric_ids=["custom_metric"],
        started_at=started,
        finished_at=started,
        duration_ms=1.0,
        results=[
            MetricResult(
                metric_id="custom_metric",
                metric_name="指标|名称",
                status="completed",
                summary="左|右\n第二行",
                observations={},
            ),
        ],
    )
    facts = build_report_fact_pack(result)
    analysis = ReportAnalysis(
        analysis_status="completed",
        analysis_model_id="report-analyzer",
        one_sentence_summary="摘要",
        overall_assessment="评估",
        metric_notes=[
            ReportAnalysisMetricNote(
                metric_id="custom_metric",
                note="备注|内容\n第二行",
                severity="medium",
            )
        ],
    )

    report_path = write_markdown_report(result, tmp_path, facts=facts, analysis=analysis)
    text = Path(report_path).read_text(encoding="utf-8")

    assert r"| 指标\|名称 | 已完成（completed） | 左\|右 第二行 |" in text
    assert r"| `custom_metric` | 备注\|内容 第二行 | medium |" in text


def test_markdown_report_redacts_secrets_in_observations_and_errors(tmp_path):
    started = utc_now()
    result = TaskResult(
        task_id="task_redaction",
        status="completed",
        model_id="demo-model",
        plan_id="gateway_baseline_v1",
        metric_ids=["connectivity"],
        started_at=started,
        finished_at=started,
        duration_ms=1.0,
        results=[
            MetricResult(
                metric_id="connectivity",
                status="error",
                summary="请求失败",
                observations={"detail": "sk-" + "secret-123456"},
                errors=[{"code": "auth", "message": "ark-" + "abcdef-123456"}],
            ),
        ],
    )
    facts = build_report_fact_pack(result)
    analysis = _completed_analysis()

    report_path = write_markdown_report(result, tmp_path, facts=facts, analysis=analysis)
    text = Path(report_path).read_text(encoding="utf-8")

    assert "secret-123456" not in text
    assert "abcdef-123456" not in text
    assert "sk-***" in text
    assert "ark-***" in text


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
