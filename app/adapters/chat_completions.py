from __future__ import annotations

import json
from typing import Any

import httpx

from app.adapters.base import BaseAdapter
from app.core.models import AdapterRequest, AdapterResponse, StreamAdapterResponse, StreamChunk
from app.utils.timing import elapsed_ms, now_monotonic


class ChatCompletionsAdapter(BaseAdapter):
    @property
    def endpoint(self) -> str:
        return f"{self.config.base_url}/chat/completions"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.config.api_key}", "Content-Type": "application/json"}

    def _body(self, request: AdapterRequest, stream: bool) -> dict[str, Any]:
        messages = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.append({"role": "user", "content": request.prompt})
        body: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": request.temperature,
            "stream": stream,
        }
        if request.max_tokens is not None:
            body["max_tokens"] = request.max_tokens
        body.update(request.extra_body)
        return body

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
            choice = (data.get("choices") or [{}])[0]
            message = choice.get("message") or {}
            content = message.get("content") or message.get("reasoning_content") or ""
            finish_reason = choice.get("finish_reason")
            ok = response.status_code < 400 and bool(content)
            error = data.get("error") if not ok else None
            return AdapterResponse(ok=ok, http_status=response.status_code, latency_ms=latency, raw=data, content=content, finish_reason=finish_reason, usage=data.get("usage"), error=error)
        except Exception as exc:
            return AdapterResponse(ok=False, latency_ms=elapsed_ms(start), error={"code": type(exc).__name__, "message": str(exc)})

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
                        choice = (data.get("choices") or [{}])[0]
                        delta_obj = choice.get("delta") or {}
                        delta = delta_obj.get("content") or delta_obj.get("reasoning_content") or ""
                        if delta and ttft is None:
                            ttft = elapsed_ms(start)
                        if delta:
                            content_parts.append(delta)
                        finish_reason = choice.get("finish_reason") or finish_reason
                        usage = data.get("usage") or usage
                        chunks.append(StreamChunk(event_index=index, elapsed_ms=elapsed_ms(start), data=data, content_delta=delta, finish_reason=choice.get("finish_reason"), usage=data.get("usage")))
                        index += 1
            full_content = "".join(content_parts)
            ok = bool(full_content) and (http_status is None or http_status < 400) and not any(c.parse_error for c in chunks)
            return StreamAdapterResponse(ok=ok, http_status=http_status, ttft_ms=ttft, end_to_end_latency_ms=elapsed_ms(start), chunks=chunks, content=full_content, finish_reason=finish_reason, usage=usage, raw_event_excerpt=raw_excerpt, error=None if ok else {"code": "stream_error", "message": "stream response failed or empty"})
        except Exception as exc:
            return StreamAdapterResponse(ok=False, http_status=http_status, end_to_end_latency_ms=elapsed_ms(start), chunks=chunks, content="".join(content_parts), finish_reason=finish_reason, usage=usage, raw_event_excerpt=raw_excerpt, error={"code": type(exc).__name__, "message": str(exc)})
