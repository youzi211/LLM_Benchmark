from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI(title="Fake OpenAI-compatible upstream")


def _extract_chat_prompt(body: dict[str, Any]) -> str:
    messages = body.get("messages") or []
    return "\n".join(str(m.get("content", "")) for m in messages)


def _maybe_error(body: dict[str, Any], authorization: str | None, prompt: str):
    if authorization and "invalid" in authorization:
        return JSONResponse({"error": {"code": "unauthorized", "message": "bad api key"}}, status_code=401)
    if str(body.get("model", "")).startswith("invalid"):
        return JSONResponse({"error": {"code": "model_not_found", "message": "bad model"}}, status_code=404)
    if prompt == "":
        return JSONResponse({"error": {"code": "empty_input", "message": "empty input"}}, status_code=400)
    if body.get("temperature") == -999:
        return JSONResponse({"error": {"code": "invalid_parameter", "message": "bad temperature"}}, status_code=400)
    if len(prompt) > 15000:
        return JSONResponse({"error": {"code": "context_overflow", "message": "context too long"}}, status_code=400)
    return None


def _content_for_prompt(prompt: str) -> str:
    if "CONTEXT_MARKER_7F3A9C" in prompt:
        return "CONTEXT_MARKER_7F3A9C"
    if "结构化中文说明文" in prompt:
        return "# 大模型 API 网关上线前验证\n\n" + "需要验证连通性、延迟、上下文、输出长度、并发、限流、错误处理和 usage。" * 8
    return "这是一个假上游响应，用于验证 LLM Benchmark 服务可执行完整基础工程评测。"


@app.post("/v1/chat/completions")
async def chat_completions(request: Request, authorization: str | None = Header(default=None)):
    body = await request.json()
    prompt = _extract_chat_prompt(body)
    error = _maybe_error(body, authorization, prompt)
    if error:
        return error
    content = _content_for_prompt(prompt)
    if body.get("stream"):
        async def events():
            for part in [content[: max(1, len(content)//2)], content[max(1, len(content)//2):]]:
                yield "data: " + json.dumps({"choices": [{"delta": {"content": part}, "finish_reason": None}]}, ensure_ascii=False) + "\n\n"
            yield "data: " + json.dumps({"choices": [{"delta": {}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 10, "completion_tokens": 12, "total_tokens": 22}}, ensure_ascii=False) + "\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(events(), media_type="text/event-stream")
    return {
        "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 12, "total_tokens": 22},
    }


@app.post("/v1/responses")
async def responses(request: Request, authorization: str | None = Header(default=None)):
    body = await request.json()
    prompt = str(body.get("input", ""))
    error = _maybe_error(body, authorization, prompt)
    if error:
        return error
    content = _content_for_prompt(prompt)
    if body.get("stream"):
        async def events():
            for part in [content[: max(1, len(content)//2)], content[max(1, len(content)//2):]]:
                yield "data: " + json.dumps({"type": "response.output_text.delta", "delta": part}, ensure_ascii=False) + "\n\n"
            yield "data: " + json.dumps({"type": "response.completed", "response": {"usage": {"input_tokens": 10, "output_tokens": 12, "total_tokens": 22}}}, ensure_ascii=False) + "\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(events(), media_type="text/event-stream")
    return {"output_text": content, "usage": {"input_tokens": 10, "output_tokens": 12, "total_tokens": 22}, "status": "completed"}
