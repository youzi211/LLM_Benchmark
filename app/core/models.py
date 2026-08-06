from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.statuses import Protocol


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ModelConfigBase(BaseModel):
    name: str
    protocol: Protocol
    base_url: str
    api_key: str
    model: str
    timeout_seconds: int = Field(default=60, ge=1, le=600)
    enabled: bool = True
    declared_context_tokens: int | None = Field(default=None, ge=1)
    declared_max_output_tokens: int | None = Field(default=None, ge=1)
    concurrency_levels: list[int] = Field(default_factory=lambda: [1, 5, 10, 20])

    @field_validator("base_url")
    @classmethod
    def strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("concurrency_levels")
    @classmethod
    def validate_concurrency_levels(cls, value: list[int]) -> list[int]:
        if not value:
            return [1, 5, 10, 20]
        cleaned = sorted(set(value))
        if any(v < 1 or v > 200 for v in cleaned):
            raise ValueError("concurrency levels must be between 1 and 200")
        return cleaned


class ModelConfigCreate(ModelConfigBase):
    id: str = Field(pattern=r"^[a-zA-Z0-9_.-]+$", min_length=1, max_length=128)


class ModelConfigUpdate(BaseModel):
    name: str | None = None
    protocol: Protocol | None = None
    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None
    timeout_seconds: int | None = Field(default=None, ge=1, le=600)
    enabled: bool | None = None
    declared_context_tokens: int | None = Field(default=None, ge=1)
    declared_max_output_tokens: int | None = Field(default=None, ge=1)
    concurrency_levels: list[int] | None = None

    @field_validator("base_url")
    @classmethod
    def strip_trailing_slash(cls, value: str | None) -> str | None:
        return value.rstrip("/") if value is not None else None

    @field_validator("concurrency_levels")
    @classmethod
    def validate_concurrency_levels(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return None
        if not value:
            return [1, 5, 10, 20]
        cleaned = sorted(set(value))
        if any(v < 1 or v > 200 for v in cleaned):
            raise ValueError("concurrency levels must be between 1 and 200")
        return cleaned


class ModelConfig(ModelConfigCreate):
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ModelConfigPublic(ModelConfig):
    api_key: str


class MetricInfo(BaseModel):
    id: str
    priority: str
    name: str
    description: str
    default_in_gateway_baseline_v1: bool


class PlanInfo(BaseModel):
    id: str
    name: str
    description: str
    metric_ids: list[str]


class RunTaskRequest(BaseModel):
    model_id: str
    plan_id: str = "gateway_acceptance_v1"
    metric_ids: list[str] | None = None


class AdapterRequest(BaseModel):
    prompt: str
    system_prompt: str | None = None
    max_tokens: int | None = None
    temperature: float = 0
    stream: bool = False
    extra_body: dict[str, Any] = Field(default_factory=dict)


class AdapterResponse(BaseModel):
    ok: bool
    http_status: int | None = None
    latency_ms: float | None = None
    raw: dict[str, Any] | None = None
    content: str = ""
    finish_reason: str | None = None
    usage: dict[str, Any] | None = None
    error: dict[str, Any] | None = None


class StreamChunk(BaseModel):
    event_index: int
    elapsed_ms: float
    data: dict[str, Any] | str | None = None
    content_delta: str = ""
    finish_reason: str | None = None
    usage: dict[str, Any] | None = None
    parse_error: str | None = None
    done: bool = False


class StreamAdapterResponse(BaseModel):
    ok: bool
    http_status: int | None = None
    ttft_ms: float | None = None
    end_to_end_latency_ms: float | None = None
    chunks: list[StreamChunk] = Field(default_factory=list)
    content: str = ""
    finish_reason: str | None = None
    usage: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    raw_event_excerpt: list[str] = Field(default_factory=list)


class MetricResult(BaseModel):
    metric_id: str
    metric_name: str | None = None
    status: Literal["completed", "error", "skipped"]
    summary: str
    observations: dict[str, Any] = Field(default_factory=dict)
    errors: list[dict[str, Any]] = Field(default_factory=list)


class TaskResult(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    task_id: str
    status: Literal["completed", "error"]
    model_id: str
    model_config_name: str | None = None
    upstream_model_name: str | None = None
    protocol: Protocol | None = None
    plan_id: str
    metric_ids: list[str]
    started_at: datetime
    finished_at: datetime | None = None
    duration_ms: float | None = None
    results: list[MetricResult] = Field(default_factory=list)
    report_path: str | None = None
    analysis_model_id: str | None = None
    analysis: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
