from __future__ import annotations

from typing import Callable

import httpx

from app.core.models import AdapterRequest, AdapterResponse, ModelConfig, StreamAdapterResponse


class BaseAdapter:
    def __init__(self, config: ModelConfig, transport: httpx.AsyncBaseTransport | httpx.BaseTransport | None = None):
        self.config = config
        self.transport = transport

    async def complete(self, request: AdapterRequest) -> AdapterResponse:
        raise NotImplementedError

    async def stream(self, request: AdapterRequest) -> StreamAdapterResponse:
        raise NotImplementedError


AdapterFactory = Callable[[ModelConfig], BaseAdapter]


def create_adapter(config: ModelConfig) -> BaseAdapter:
    if config.protocol == "chat_completions":
        from app.adapters.chat_completions import ChatCompletionsAdapter

        return ChatCompletionsAdapter(config)
    if config.protocol == "responses":
        from app.adapters.responses import ResponsesAdapter

        return ResponsesAdapter(config)
    raise ValueError(f"invalid_protocol:{config.protocol}")
