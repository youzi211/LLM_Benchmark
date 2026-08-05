import json

import httpx
import pytest

from app.core.models import AdapterRequest, ModelConfig


def model_config(protocol="chat_completions"):
    return ModelConfig(
        id="m1",
        name="M1",
        protocol=protocol,
        base_url="http://upstream.test/v1/",
        api_key="sk-secret",
        model="model-a",
    )


@pytest.mark.asyncio
async def test_chat_completions_adapter_normalizes_non_stream_response():
    from app.adapters.chat_completions import ChatCompletionsAdapter

    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["auth"] = request.headers.get("authorization")
        payload = json.loads(request.content.decode("utf-8"))
        seen["stream"] = payload["stream"]
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "hello"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
        })

    adapter = ChatCompletionsAdapter(model_config(), transport=httpx.MockTransport(handler))
    response = await adapter.complete(AdapterRequest(prompt="hi"))

    assert seen == {"path": "/v1/chat/completions", "auth": "Bearer sk-secret", "stream": False}
    assert response.ok is True
    assert response.content == "hello"
    assert response.finish_reason == "stop"
    assert response.usage["total_tokens"] == 7


@pytest.mark.asyncio
async def test_responses_adapter_normalizes_non_stream_response():
    from app.adapters.responses import ResponsesAdapter

    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["auth"] = request.headers.get("authorization")
        payload = json.loads(request.content.decode("utf-8"))
        seen["stream"] = payload["stream"]
        return httpx.Response(200, json={
            "output_text": "response text",
            "usage": {"input_tokens": 5, "output_tokens": 6, "total_tokens": 11},
        })

    adapter = ResponsesAdapter(model_config("responses"), transport=httpx.MockTransport(handler))
    response = await adapter.complete(AdapterRequest(prompt="hi"))

    assert seen == {"path": "/v1/responses", "auth": "Bearer sk-secret", "stream": False}
    assert response.ok is True
    assert response.content == "response text"
    assert response.usage["total_tokens"] == 11


@pytest.mark.asyncio
async def test_chat_stream_combines_sse_content():
    from app.adapters.chat_completions import ChatCompletionsAdapter

    def handler(request: httpx.Request) -> httpx.Response:
        body = "\n\n".join([
            'data: {"choices":[{"delta":{"content":"你"}}]}',
            'data: {"choices":[{"delta":{"content":"好"},"finish_reason":"stop"}],"usage":{"completion_tokens":2}}',
            'data: [DONE]',
            '',
        ])
        return httpx.Response(200, content=body.encode("utf-8"), headers={"content-type": "text/event-stream"})

    adapter = ChatCompletionsAdapter(model_config(), transport=httpx.MockTransport(handler))
    response = await adapter.stream(AdapterRequest(prompt="hi", stream=True))

    assert response.ok is True
    assert response.content == "你好"
    assert response.ttft_ms is not None
    assert response.end_to_end_latency_ms is not None
    assert response.finish_reason == "stop"
    assert any(chunk.done for chunk in response.chunks)


@pytest.mark.asyncio
async def test_chat_completions_adapter_falls_back_to_reasoning_content_when_content_empty():
    from app.adapters.chat_completions import ChatCompletionsAdapter

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "", "reasoning_content": "reasoning answer"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
        })

    adapter = ChatCompletionsAdapter(model_config(), transport=httpx.MockTransport(handler))
    response = await adapter.complete(AdapterRequest(prompt="hi"))

    assert response.ok is True
    assert response.content == "reasoning answer"
