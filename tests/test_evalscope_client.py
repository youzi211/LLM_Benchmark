import json

import httpx
import pytest

from app.intelligence.evalscope_client import EvalScopeClient, EvalScopeClientError
from app.intelligence.schemas import EvalScopeConfig


@pytest.mark.asyncio
async def test_evalscope_client_uses_expected_paths_and_payloads():
    seen = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode() or "{}") if request.content else None
        seen.append((request.method, request.url.path, payload))
        if request.url.path.endswith("/eval/default"):
            return httpx.Response(200, json={"task_id": "eval-1", "status": "pending"})
        if request.url.path.endswith("/eval"):
            return httpx.Response(200, json={"task_id": "eval-2", "status": "pending"})
        return httpx.Response(200, json={"ok": True})

    client = EvalScopeClient(EvalScopeConfig(base_url="http://evalscope/api/v1"), transport=httpx.MockTransport(handler))

    assert await client.health() == {"ok": True}
    assert (await client.submit_default(model="m", api_url="http://api", api_key="key"))["task_id"] == "eval-1"
    await client.submit_custom(model="m", api_url="http://api", api_key="key", datasets=["gsm8k"], limit=3, eval_batch_size=2)
    await client.task_status("eval-1")
    await client.task_result("eval-1")

    assert ("GET", "/api/v1/health", None) in seen
    assert ("POST", "/api/v1/eval/default", {"model": "m", "api_url": "http://api", "api_key": "key"}) in seen
    assert any(item[1] == "/api/v1/tasks/eval-1/result" for item in seen)


@pytest.mark.asyncio
async def test_evalscope_client_redacts_http_errors():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="bad " + "sk" + "-example-token")

    client = EvalScopeClient(EvalScopeConfig(), transport=httpx.MockTransport(handler))

    with pytest.raises(EvalScopeClientError) as exc_info:
        await client.health()

    assert "sk" + "-example-token" not in str(exc_info.value)
    assert "sk" + "-***" in str(exc_info.value)
    assert exc_info.value.status_code == 400
