from __future__ import annotations

import pytest

from app.adapters.base import BaseAdapter
from app.core.models import AdapterRequest, AdapterResponse, ModelConfig
from app.metrics.probes import run_cache_behavior_probe


class CacheAwareAdapter(BaseAdapter):
    def __init__(self, config: ModelConfig):
        super().__init__(config)
        self.requests: list[AdapterRequest] = []

    async def complete(self, request: AdapterRequest) -> AdapterResponse:
        self.requests.append(request)
        index = len(self.requests)
        cached_tokens = 0 if index == 1 else 1536
        return AdapterResponse(
            ok=True,
            http_status=200,
            latency_ms=300 if index == 1 else 120,
            raw={"id": f"resp-{index}"},
            content=f"cache round {index}",
            finish_reason="stop",
            usage={
                "prompt_tokens": 2048,
                "completion_tokens": 16,
                "total_tokens": 2064,
                "prompt_tokens_details": {"cached_tokens": cached_tokens},
            },
        )


@pytest.mark.asyncio
async def test_cache_behavior_probe_reuses_prefix_and_extracts_cache_tokens():
    config = ModelConfig(
        id="demo-cache",
        name="Demo Cache",
        protocol="chat_completions",
        base_url="http://fake/v1",
        api_key="dummy-test-key",
        model="demo-model",
        declared_context_tokens=8192,
        declared_max_output_tokens=256,
    )
    adapter = CacheAwareAdapter(config)

    result = await run_cache_behavior_probe(adapter, config)

    assert result.metric_id == "cache_behavior"
    assert result.status == "completed"
    assert len(adapter.requests) == 3
    common_prefix = adapter.requests[0].prompt[:1000]
    assert all(req.prompt.startswith(common_prefix) for req in adapter.requests)
    assert result.observations["request_count"] == 3
    assert result.observations["cache_signal_present"] is True
    assert result.observations["max_cached_tokens"] == 1536
    assert result.observations["cache_hit_count"] == 2
    assert "prompt_tokens_details.cached_tokens" in result.observations["usage_field_paths_detected"]
    assert result.observations["latency_baseline_ms"] == 300
    assert result.observations["repeated_latency_avg_ms"] == 120


class NoCacheSignalAdapter(BaseAdapter):
    async def complete(self, request: AdapterRequest) -> AdapterResponse:
        return AdapterResponse(
            ok=True,
            http_status=200,
            latency_ms=200,
            raw={"ok": True},
            content="ok",
            finish_reason="stop",
            usage={"prompt_tokens": 1024, "completion_tokens": 8, "total_tokens": 1032},
        )


@pytest.mark.asyncio
async def test_cache_behavior_probe_completes_without_provider_cache_fields():
    config = ModelConfig(
        id="demo-no-cache-fields",
        name="Demo No Cache Fields",
        protocol="responses",
        base_url="http://fake/v1",
        api_key="dummy-test-key",
        model="demo-model",
    )

    result = await run_cache_behavior_probe(NoCacheSignalAdapter(config), config)

    assert result.status == "completed"
    assert result.observations["cache_signal_present"] is False
    assert result.observations["max_cached_tokens"] is None
    assert result.observations["cache_hit_count"] == 0
    assert result.errors == []
