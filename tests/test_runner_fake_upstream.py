from pathlib import Path

import pytest

from app.core.models import AdapterRequest, AdapterResponse, ModelConfig, StreamAdapterResponse, StreamChunk


class FakeAdapter:
    def __init__(self, config: ModelConfig):
        self.config = config

    async def complete(self, request: AdapterRequest) -> AdapterResponse:
        if self.config.api_key.startswith("invalid"):
            return AdapterResponse(ok=False, http_status=401, latency_ms=1, error={"code": "unauthorized", "message": "bad key"})
        if self.config.model.startswith("invalid"):
            return AdapterResponse(ok=False, http_status=404, latency_ms=1, error={"code": "model_not_found", "message": "bad model"})
        if request.prompt == "":
            return AdapterResponse(ok=False, http_status=400, latency_ms=1, error={"code": "empty_input", "message": "empty"})
        if request.extra_body.get("temperature") == -999:
            return AdapterResponse(ok=False, http_status=400, latency_ms=1, error={"code": "invalid_parameter", "message": "bad temperature"})
        if len(request.prompt) > 30000:
            return AdapterResponse(ok=False, http_status=400, latency_ms=2, error={"code": "context_overflow", "message": "too long"})
        content = "CONTEXT_MARKER_7F3A9C" if "CONTEXT_MARKER_7F3A9C" in request.prompt else "这是一个可用响应，用于工程评测。"
        return AdapterResponse(
            ok=True,
            http_status=200,
            latency_ms=5,
            raw={"ok": True},
            content=content,
            finish_reason="stop",
            usage={"prompt_tokens": 10, "completion_tokens": 8, "total_tokens": 18},
        )

    async def stream(self, request: AdapterRequest) -> StreamAdapterResponse:
        chunks = [
            StreamChunk(event_index=0, elapsed_ms=2, data={"delta": "一"}, content_delta="一"),
            StreamChunk(event_index=1, elapsed_ms=4, data={"delta": "二"}, content_delta="二", finish_reason="stop", usage={"completion_tokens": 2}),
            StreamChunk(event_index=2, elapsed_ms=5, data="[DONE]", done=True),
        ]
        return StreamAdapterResponse(
            ok=True,
            http_status=200,
            ttft_ms=2,
            end_to_end_latency_ms=5,
            chunks=chunks,
            content="一二",
            finish_reason="stop",
            usage={"completion_tokens": 2},
            raw_event_excerpt=['data: {"delta":"一"}', 'data: [DONE]'],
        )


@pytest.mark.asyncio
async def test_runner_executes_full_gateway_plan_and_writes_report(tmp_path):
    from app.core.models import ModelConfigCreate
    from app.core.runner import TaskRunner
    from app.storage.model_store import ModelStore
    from app.storage.task_store import TaskStore

    model_store = ModelStore(tmp_path / "data" / "models.json")
    task_store = TaskStore(tmp_path / "data" / "tasks")
    model_store.create(ModelConfigCreate(
        id="demo-chat",
        name="Demo Chat",
        protocol="chat_completions",
        base_url="http://fake/v1",
        api_key="sk-super-secret",
        model="demo-model",
        declared_context_tokens=4096,
        declared_max_output_tokens=256,
        concurrency_levels=[1, 2],
    ))

    runner = TaskRunner(
        model_store=model_store,
        task_store=task_store,
        reports_dir=tmp_path / "reports",
        adapter_factory=lambda config: FakeAdapter(config),
    )
    result = await runner.run(model_id="demo-chat", plan_id="gateway_baseline_v1")

    assert result.status == "completed"
    assert result.model_config_name == "Demo Chat"
    assert result.upstream_model_name == "demo-model"
    assert result.protocol == "chat_completions"
    assert {r.metric_id for r in result.results} == {
        "connectivity", "latency_breakdown", "context_length", "output_length",
        "concurrency", "rate_limit", "error_handling", "token_usage_accuracy", "stream_spec",
    }
    assert result.report_path is not None
    report_path = Path(result.report_path)
    assert report_path.exists()
    text = report_path.read_text(encoding="utf-8")
    assert "- 模型配置名称：`Demo Chat`" in text
    assert "- API 模型名称（model）：`demo-model`" in text
    assert "本地 token 数为估算值" in text
    assert "sk-" not in text
    assert task_store.get(result.task_id).task_id == result.task_id
