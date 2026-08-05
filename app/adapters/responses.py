from __future__ import annotations

import json
from typing import Any

import httpx

from app.adapters.base import BaseAdapter
from app.core.models import AdapterRequest, AdapterResponse, StreamAdapterResponse, StreamChunk
from app.utils.timing import elapsed_ms, now_monotonic


class ResponsesAdapter(BaseAdapter):
    @property
    def endpoint(self) -> str:
        return f"{self.config.base_url}/responses"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.config.api_key}", "Content-Type": "application/json"}

    def _body(self, request: AdapterRequest, stream: bool) -> dict[str, Any]:
        body: dict[str, Any] = {"model": self.config.model, "input": request.prompt, "temperature": request.temperature, "stream": stream}
        if request.system_prompt:
            body["instructions"] = request.system_prompt
        if request.max_tokens is not None:
            body["max_output_tokens"] = request.max_tokens
        body.update(request.extra_body)
        return body

    @staticmethod
    def _extract_content(data: dict[str, Any]) -> str:
        if isinstance(data.get("output_text"), str):
            return data["output_text"]
        parts: list[str] = []
        for item in data.get("output") or []:
            for content in item.get("content") or []:
                text = content.get("text") if isinstance(content, dict) else None
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)

    async def complete(self, request: AdapterRequest) -> AdapterResponse:
        start = now_monotonic()
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout_seconds, transport=self.transport) as client:
                response = await client.post(self.endpoint, headers=self._headers(), json=self._body(request, False))
            latency = elapsed_ms(start)
            try:
                data = response.json()
            except Exception as exc:
                return AdapterResponse(ok=False, http_status=response.status_code, latency_ms=latency, error={"code": "json_parse_error", "message": str(exc)})
            content = self._extract_content(data)
            finish_reason = data.get("status") or data.get("finish_reason")
            ok = response.status_code < 400 and bool(content)
            return AdapterResponse(ok=ok, http_status=response.status_code, latency_ms=latency, raw=data, content=content, finish_reason=finish_reason, usage=data.get("usage"), error=data.get("error") if not ok else None)
        except Exception as exc:
            return AdapterResponse(ok=False, latency_ms=elapsed_ms(start), error={"code": type(exc).__name__, "message": str(exc)})

    @staticmethod
    def _extract_delta(data: dict[str, Any]) -> str:
        if isinstance(data.get("delta"), str):
            return data["delta"]
        if isinstance(data.get("text"), str):
            return data["text"]
        if data.get("type") == "response.output_text.delta" and isinstance(data.get("delta"), str):
            return data["delta"]
        return ""

    async def stream(self, request: AdapterRequest) -> StreamAdapterResponse:
        start = now_monotonic()
        chunks: list[StreamChunk] = []
        raw_excerpt: list[str] = []
        content_parts: list[str] = []
        finish_reason = None
        usage = None
        ttft = None
        http_status = None
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout_seconds, transport=self.transport) as client:
                async with client.stream("POST", self.endpoint, headers=self._headers(), json=self._body(request, True)) as response:
                    http_status = response.status_code
                    index = 0
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        payload = line[5:].strip()
                        if len(raw_excerpt) < 5:
                            raw_excerpt.append(f"data: {payload}")
                        if payload == "[DONE]":
                            chunks.append(StreamChunk(event_index=index, elapsed_ms=elapsed_ms(start), data="[DONE]", done=True))
                            index += 1
                            continue
                        try:
                            data = json.loads(payload)
                        except Exception as exc:
                            chunks.append(StreamChunk(event_index=index, elapsed_ms=elapsed_ms(start), data=payload, parse_error=str(exc)))
                            index += 1
                            continue
                        delta = self._extract_delta(data)
                        if delta and ttft is None:
                            ttft = elapsed_ms(start)
                        if delta:
                            content_parts.append(delta)
                        if data.get("type") in {"response.completed", "response.output_item.done"}:
                            finish_reason = data.get("type")
                        usage = data.get("usage") or (data.get("response") or {}).get("usage") or usage
                        chunks.append(StreamChunk(event_index=index, elapsed_ms=elapsed_ms(start), data=data, content_delta=delta, finish_reason=finish_reason, usage=usage))
                        index += 1
            full_content = "".join(content_parts)
            ok = bool(full_content) and (http_status is None or http_status < 400) and not any(c.parse_error for c in chunks)
            return StreamAdapterResponse(ok=ok, http_status=http_status, ttft_ms=ttft, end_to_end_latency_ms=elapsed_ms(start), chunks=chunks, content=full_content, finish_reason=finish_reason, usage=usage, raw_event_excerpt=raw_excerpt, error=None if ok else {"code": "stream_error", "message": "stream response failed or empty"})
        except Exception as exc:
            return StreamAdapterResponse(ok=False, http_status=http_status, end_to_end_latency_ms=elapsed_ms(start), chunks=chunks, content="".join(content_parts), finish_reason=finish_reason, usage=usage, raw_event_excerpt=raw_excerpt, error={"code": type(exc).__name__, "message": str(exc)})
