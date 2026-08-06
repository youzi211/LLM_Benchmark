from __future__ import annotations

from typing import Any

import httpx

from app.intelligence.schemas import EvalScopeConfig
from app.reports.markdown import redact_text


class EvalScopeClientError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None, details: Any | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details


class EvalScopeClient:
    def __init__(
        self,
        config: EvalScopeConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_seconds: int | None = None,
    ):
        self.config = config
        self.transport = transport
        self.timeout_seconds = timeout_seconds or config.default_timeout_seconds

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        timeout = httpx.Timeout(self.timeout_seconds)
        async with httpx.AsyncClient(base_url=self.config.base_url, timeout=timeout, transport=self.transport) as client:
            response = await client.request(method, path, **kwargs)
        if response.status_code < 200 or response.status_code >= 300:
            text = redact_text(response.text)
            raise EvalScopeClientError(f"EvalScope HTTP {response.status_code}: {text}", response.status_code, text)
        try:
            return response.json()
        except ValueError as exc:
            raise EvalScopeClientError(f"EvalScope returned non-JSON response: {redact_text(response.text)}", response.status_code) from exc

    async def health(self) -> dict[str, Any]:
        return await self._request("GET", "/health")

    async def judge_config(self) -> dict[str, Any]:
        return await self._request("GET", "/judge-config")

    async def datasets(self) -> dict[str, Any]:
        return await self._request("GET", "/datasets")

    async def local_datasets(self) -> dict[str, Any]:
        return await self._request("GET", "/datasets/local")

    async def submit_default(self, *, model: str, api_url: str, api_key: str) -> dict[str, Any]:
        return await self._request("POST", "/eval/default", json={"model": model, "api_url": api_url, "api_key": api_key})

    async def submit_custom(
        self,
        *,
        model: str,
        api_url: str,
        api_key: str,
        datasets: list[str],
        limit: int | None = None,
        eval_batch_size: int | None = None,
        generation_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"model": model, "api_url": api_url, "api_key": api_key, "datasets": datasets}
        if limit is not None:
            payload["limit"] = limit
        if eval_batch_size is not None:
            payload["eval_batch_size"] = eval_batch_size
        if generation_config is not None:
            payload["generation_config"] = generation_config
        return await self._request("POST", "/eval", json=payload)

    async def tasks(self) -> list[dict[str, Any]] | dict[str, Any]:
        return await self._request("GET", "/tasks")

    async def task_status(self, evalscope_task_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/tasks/{evalscope_task_id}")

    async def task_result(self, evalscope_task_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/tasks/{evalscope_task_id}/result")
