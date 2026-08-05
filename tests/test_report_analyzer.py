from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.adapters.base import BaseAdapter
from app.core.models import AdapterRequest, AdapterResponse, ModelConfig

from app.reports.analyzer import ReportAnalyzer, extract_json_object
from app.reports.schemas import (
    ReportAnalysis,
    ReportAnalysisMetricNote,
    ReportFactPack,
    ReportMetricFact,
    ReportStatusCounts,
    ReportTaskFacts,
)
from app.storage.model_store import ModelStore


def _make_model_config(model_id: str = "report-analyzer") -> ModelConfig:
    return ModelConfig(
        id=model_id,
        name="Report Analyzer",
        protocol="chat_completions",
        base_url="http://localhost:8000/v1",
        api_key="sk" + "-test-analysis-key",
        model="gpt-4o-mini",
    )


def _make_fact_pack() -> ReportFactPack:
    return ReportFactPack(
        task=ReportTaskFacts(
            task_id="task-1",
            model_id="minimax-m3-ark-real",
            model_config_name="MiniMax-M3",
            upstream_model_name="minimax-m3",
            protocol="chat_completions",
            plan_id="gateway_baseline_v1",
            duration_ms=120.0,
        ),
        status_counts=ReportStatusCounts(total=1, completed=1),
        metric_facts=[
            ReportMetricFact(
                metric_id="connectivity",
                metric_name="连通性",
                status="completed",
                summary="连通性探测完成",
                core_observation="HTTP 200，延迟 120 ms。",
                suggested_focus="复核核心观测，确保无回归。",
            )
        ],
    )


class FakeAdapter(BaseAdapter):
    def __init__(
        self,
        response: AdapterResponse | None = None,
        exc: Exception | None = None,
    ):
        # Bypass BaseAdapter __init__ to avoid requiring a ModelConfig/transport.
        self.config = None
        self.transport = None
        self.response = response
        self.exc = exc
        self.requests: list[AdapterRequest] = []

    async def complete(self, request: AdapterRequest) -> AdapterResponse:
        self.requests.append(request)
        if self.exc is not None:
            raise self.exc
        if self.response is None:
            raise RuntimeError("FakeAdapter configured without response or exc")
        return self.response

    async def stream(self, request: AdapterRequest) -> None:  # pragma: no cover
        raise NotImplementedError


def _store_with_analysis_model(tmp_path: Path, model_id: str | None) -> ModelStore:
    store = ModelStore(path=tmp_path / "models.json")
    if model_id is not None:
        store.create(_make_model_config(model_id))
        store.set_analysis_model_id(model_id)
    return store


# ---------------------------------------------------------------------------
# extract_json_object
# ---------------------------------------------------------------------------
def test_extract_json_object_plain():
    payload = '{"status":"completed","summary":"ok"}'
    assert extract_json_object(payload) == payload


def test_extract_json_object_fenced_json():
    text = "```json\n{\"status\": \"completed\"}\n```"
    assert extract_json_object(text) == '{"status": "completed"}'


def test_extract_json_object_fenced_without_language():
    text = "```\n{\"status\": \"completed\"}\n```"
    assert extract_json_object(text) == '{"status": "completed"}'


def test_extract_json_object_from_prose():
    text = (
        "Here is the analysis result:\n"
        '{"status": "completed", "summary": "ok"}\n'
        "Hope this helps."
    )
    assert extract_json_object(text) == '{"status": "completed", "summary": "ok"}'


def test_extract_json_object_nested_braces():
    text = 'prefix {"outer": {"inner": 1}} suffix'
    assert extract_json_object(text) == '{"outer": {"inner": 1}}'


def test_extract_json_object_stops_at_first_balanced_object():
    text = '{"a": 1} trailing }'
    assert extract_json_object(text) == '{"a": 1}'


def test_extract_json_object_prefers_first_object():
    text = '{"a": 1} ... {"b": 2}'
    assert extract_json_object(text) == '{"a": 1}'


def test_extract_json_object_braces_inside_string():
    text = '{"a": "{nested}"}'
    assert extract_json_object(text) == '{"a": "{nested}"}'


def test_extract_json_object_escaped_quotes_inside_string():
    text = r'{"a": "say \"hello\""}'
    assert extract_json_object(text) == r'{"a": "say \"hello\""}'


def test_extract_json_object_ignores_closed_think_block_before_json():
    text = (
        "<think>我先构思一个草稿：\n{report_meta: ...}\n这不是最终 JSON。</think>\n"
        '{"one_sentence_summary": "上下文测试被 TPM 限流遮挡。"}'
    )

    assert extract_json_object(text) == '{"one_sentence_summary": "上下文测试被 TPM 限流遮挡。"}'


def test_extract_json_object_no_json_raises():
    with pytest.raises(ValueError):
        extract_json_object("there is no json here")


def test_extract_json_object_missing_closing_brace_raises():
    with pytest.raises(ValueError):
        extract_json_object('{"status": "completed"')


# ---------------------------------------------------------------------------
# ReportAnalyzer
# ---------------------------------------------------------------------------
async def test_analyze_success_with_configured_model(tmp_path: Path):
    store = _store_with_analysis_model(tmp_path, "report-analyzer")
    analysis_payload = {
        "one_sentence_summary": "模型连通性正常。",
        "overall_assessment": "整体表现符合预期。",
        "key_findings": ["连通性探测通过。"],
        "risks": [],
        "recommended_next_steps": ["继续观察。"],
        "metric_notes": [
            {"metric_id": "connectivity", "note": "无异常", "severity": "info"}
        ],
    }
    adapter = FakeAdapter(
        AdapterResponse(ok=True, content=json.dumps(analysis_payload, ensure_ascii=False))
    )
    analyzer = ReportAnalyzer(store, adapter_factory=lambda _config: adapter)

    analysis = await analyzer.analyze(_make_fact_pack())

    assert isinstance(analysis, ReportAnalysis)
    assert analysis.analysis_status == "completed"
    assert analysis.analysis_model_id == "report-analyzer"
    assert analysis.one_sentence_summary == "模型连通性正常。"
    assert analysis.metric_notes[0] == ReportAnalysisMetricNote(
        metric_id="connectivity", note="无异常", severity="info"
    )
    assert len(adapter.requests) == 1
    request = adapter.requests[0]
    assert "不要判断模型是否允许上线" in request.system_prompt
    assert "one_sentence_summary" in request.system_prompt
    assert "overall_assessment" in request.system_prompt
    assert "不要输出 <think>" in request.system_prompt
    assert "test-analysis-key" not in request.prompt


async def test_analyze_missing_config_returns_skipped(tmp_path: Path):
    store = _store_with_analysis_model(tmp_path, None)
    analyzer = ReportAnalyzer(store)

    analysis = await analyzer.analyze(_make_fact_pack())

    assert analysis.analysis_status == "skipped"
    assert "未配置报告分析模型" in analysis.overall_assessment
    assert analysis.analysis_model_id is None


async def test_analyze_configured_model_missing_returns_error(tmp_path: Path):
    store = ModelStore(path=tmp_path / "models.json")
    # Write analysis_model_id pointing to a model that does not exist.
    store._write([], "report-analyzer")
    analyzer = ReportAnalyzer(store)

    analysis = await analyzer.analyze(_make_fact_pack())

    assert analysis.analysis_status == "error"
    assert analysis.analysis_model_id == "report-analyzer"
    assert "报告分析模型不存在" in analysis.error_message


async def test_analyze_invalid_json_returns_error(tmp_path: Path):
    store = _store_with_analysis_model(tmp_path, "report-analyzer")
    adapter = FakeAdapter(AdapterResponse(ok=True, content="not valid json {\"broken\""))
    analyzer = ReportAnalyzer(store, adapter_factory=lambda _config: adapter)

    analysis = await analyzer.analyze(_make_fact_pack())

    assert analysis.analysis_status == "error"
    assert analysis.analysis_model_id == "report-analyzer"
    assert "解析失败" in analysis.error_message
    assert analysis.raw_excerpt is not None


async def test_analyze_schema_validation_failure_returns_error(tmp_path: Path):
    store = _store_with_analysis_model(tmp_path, "report-analyzer")
    adapter = FakeAdapter(AdapterResponse(ok=True, content='{"metric_notes": "not a list"}'))
    analyzer = ReportAnalyzer(store, adapter_factory=lambda _config: adapter)

    analysis = await analyzer.analyze(_make_fact_pack())

    assert analysis.analysis_status == "error"
    assert analysis.analysis_model_id == "report-analyzer"
    assert "校验失败" in analysis.error_message


async def test_analyze_adapter_exception_redacts_secrets(tmp_path: Path):
    store = _store_with_analysis_model(tmp_path, "report-analyzer")
    live_key = "sk" + "-live-abc123def456"
    ark_key = "ark" + "-api-xyz789secret"
    exc_message = f"Connection failed: {live_key} and {ark_key} are both leaked in this error"
    adapter = FakeAdapter(exc=RuntimeError(exc_message))
    analyzer = ReportAnalyzer(store, adapter_factory=lambda _config: adapter)

    analysis = await analyzer.analyze(_make_fact_pack())

    assert analysis.analysis_status == "error"
    assert analysis.analysis_model_id == "report-analyzer"

    for field in (analysis.error_message, analysis.overall_assessment):
        assert live_key not in field
        assert ark_key not in field
        assert "sk-***" in field
        assert "ark-***" in field

    assert analysis.raw_excerpt is None


async def test_analyze_upstream_error_returns_error_with_redacted_excerpt(tmp_path: Path):
    store = _store_with_analysis_model(tmp_path, "report-analyzer")
    adapter = FakeAdapter(
        AdapterResponse(
            ok=False,
            http_status=500,
            content="boom",
            error={"message": "Internal server error"},
        )
    )
    analyzer = ReportAnalyzer(store, adapter_factory=lambda _config: adapter)

    analysis = await analyzer.analyze(_make_fact_pack())

    assert analysis.analysis_status == "error"
    assert analysis.analysis_model_id == "report-analyzer"
    assert analysis.raw_excerpt is not None
    assert ("sk" + "-test-analysis-key") not in (analysis.raw_excerpt or "")

