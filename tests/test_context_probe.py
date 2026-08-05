import pytest

from app.core.models import AdapterRequest, AdapterResponse, ModelConfig
from app.metrics.probes import _context_points, run_context_length_probe


class MarkerMissAdapter:
    async def complete(self, request: AdapterRequest) -> AdapterResponse:
        return AdapterResponse(
            ok=True,
            http_status=200,
            latency_ms=12.5,
            content="我看到了背景资料，但没有按要求复述标记。",
            finish_reason="stop",
            usage={"prompt_tokens": 1234, "completion_tokens": 18, "total_tokens": 1252},
        )


class MarkerSpacedAdapter:
    async def complete(self, request: AdapterRequest) -> AdapterResponse:
        return AdapterResponse(
            ok=True,
            http_status=200,
            latency_ms=10,
            content="ZXQ 7F3A9C END",
            finish_reason="stop",
            usage={"prompt_tokens": 4096, "completion_tokens": 8, "total_tokens": 4104},
        )


@pytest.mark.asyncio
async def test_context_probe_records_content_excerpt_and_usage_when_marker_missing():
    config = ModelConfig(
        id="ctx-demo",
        name="Context Demo",
        protocol="chat_completions",
        base_url="http://fake/v1",
        api_key="sk-test",
        model="demo-model",
        declared_context_tokens=4096,
    )

    result = await run_context_length_probe(MarkerMissAdapter(), config)

    assert result.status == "error"
    first = result.observations["point_results"][0]
    assert first["http_status"] == 200
    assert first["marker_found"] is False
    assert first["content_excerpt"] == "我看到了背景资料，但没有按要求复述标记。"
    assert first["finish_reason"] == "stop"
    assert first["usage_prompt_tokens"] == 1234
    assert first["usage_completion_tokens"] == 18
    assert first["usage_total_tokens"] == 1252


def test_context_points_use_finer_buckets_for_large_context_window():
    assert _context_points(1048576) == [
        4096,
        8192,
        16384,
        32768,
        65536,
        131072,
        262144,
        524288,
        786432,
        943718,
        1048576,
    ]


@pytest.mark.asyncio
async def test_context_probe_accepts_minor_marker_format_variants():
    config = ModelConfig(
        id="ctx-demo",
        name="Context Demo",
        protocol="chat_completions",
        base_url="http://fake/v1",
        api_key="sk-test",
        model="demo-model",
        declared_context_tokens=4096,
    )

    result = await run_context_length_probe(MarkerSpacedAdapter(), config)

    assert result.status == "completed"
    first = result.observations["point_results"][0]
    assert first["marker_found"] is True
    assert first["content_excerpt"] == "ZXQ 7F3A9C END"

class RecordingSuccessAdapter:
    def __init__(self):
        self.requests: list[AdapterRequest] = []

    async def complete(self, request: AdapterRequest) -> AdapterResponse:
        self.requests.append(request)
        return AdapterResponse(
            ok=True,
            http_status=200,
            latency_ms=8,
            content="ZXQ-7F3A9C-END",
            finish_reason="stop",
            usage={"prompt_tokens": 4096, "completion_tokens": 8, "total_tokens": 4104},
        )


class SequentialContextAdapter:
    def __init__(self):
        self.requests: list[AdapterRequest] = []

    async def complete(self, request: AdapterRequest) -> AdapterResponse:
        self.requests.append(request)
        index = len(self.requests)
        if index == 1:
            return AdapterResponse(ok=True, http_status=200, content="ZXQ-7F3A9C-END", usage={"prompt_tokens": 4096})
        if index == 2:
            return AdapterResponse(ok=True, http_status=200, content="没有找到指定代码", usage={"prompt_tokens": 8192})
        return AdapterResponse(
            ok=False,
            http_status=400,
            content="",
            error={"code": "InvalidParameter", "message": "context window exceeds limit"},
        )


@pytest.mark.asyncio
async def test_context_probe_uses_structured_needle_prompt_and_larger_answer_budget():
    config = ModelConfig(
        id="ctx-demo",
        name="Context Demo",
        protocol="chat_completions",
        base_url="http://fake/v1",
        api_key="sk-test",
        model="demo-model",
        declared_context_tokens=4096,
    )
    adapter = RecordingSuccessAdapter()

    result = await run_context_length_probe(adapter, config)

    assert result.status == "completed"
    assert adapter.requests[0].max_tokens == 256
    prompt = adapter.requests[0].prompt
    assert "NEEDLE_CODE:" in prompt
    assert "ZXQ-7F3A9C-END" in prompt
    assert "BEGIN_CONTEXT_BLOCK" in prompt
    assert "背景资料：测测测" not in prompt
    assert result.observations["observed_accepted_max_prompt_tokens"] == 4096
    assert result.observations["observed_marker_found_max_prompt_tokens"] == 4096
    assert result.observations["first_http_error_point"] is None
    assert result.observations["first_marker_miss_point"] is None


@pytest.mark.asyncio
async def test_context_probe_separates_acceptance_retrieval_and_stops_after_hard_http_error():
    config = ModelConfig(
        id="ctx-demo",
        name="Context Demo",
        protocol="chat_completions",
        base_url="http://fake/v1",
        api_key="sk-test",
        model="demo-model",
        declared_context_tokens=32768,
    )
    adapter = SequentialContextAdapter()

    result = await run_context_length_probe(adapter, config)

    assert result.status == "error"
    assert len(adapter.requests) == 3
    assert len(result.observations["point_results"]) == 3
    assert result.observations["observed_accepted_max_prompt_tokens"] == 8192
    assert result.observations["observed_marker_found_max_prompt_tokens"] == 4096
    assert result.observations["first_marker_miss_point"] == 8192
    assert result.observations["first_http_error_point"] == 16384
    assert result.observations["stopped_after_hard_error"] is True
    assert result.observations["point_results"][1]["accepted_by_api"] is True
    assert result.observations["point_results"][1]["retrieval_ok"] is False
    assert result.observations["point_results"][2]["accepted_by_api"] is False

