from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.models import utc_now

IntelligenceTaskStatus = Literal["pending", "running", "completed", "failed"]


class EvalScopeConfig(BaseModel):
    base_url: str = "http://localhost:8010/api/v1"
    poll_interval_seconds: int = Field(default=5, ge=1, le=3600)
    default_timeout_seconds: int = Field(default=14400, ge=1, le=86400)

    @field_validator("base_url")
    @classmethod
    def strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")


class IntelligenceDefaultRunRequest(BaseModel):
    model_id: str


class IntelligenceRunRequest(BaseModel):
    model_id: str
    datasets: list[str] = Field(min_length=1)
    limit: int | None = Field(default=None, ge=1)
    eval_batch_size: int | None = Field(default=None, ge=1)
    generation_config: dict[str, Any] | None = None


class IntelligenceDatasetResult(BaseModel):
    dataset: str
    pretty_name: str | None = None
    categories: list[str] = Field(default_factory=list)
    needs_judge: bool | None = None
    score: float | None = None
    metrics: list[dict[str, Any]] = Field(default_factory=list)
    raw_report: dict[str, Any] = Field(default_factory=dict)


class IntelligenceCategorySummary(BaseModel):
    category: str
    dataset_count: int
    scored_dataset_count: int
    average_score: float | None = None


class IntelligenceNormalizedResult(BaseModel):
    task_id: str
    evalscope_task_id: str | None = None
    model: str | None = None
    datasets: list[str] = Field(default_factory=list)
    status: str | None = None
    dataset_results: list[IntelligenceDatasetResult] = Field(default_factory=list)
    category_summaries: list[IntelligenceCategorySummary] = Field(default_factory=list)
    report_table: str | None = None
    error: str | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None


class IntelligenceTask(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    task_id: str
    evalscope_task_id: str | None = None
    model_id: str
    model_config_name: str | None = None
    upstream_model_name: str | None = None
    evalscope_base_url: str
    datasets: list[str] = Field(default_factory=list)
    status: IntelligenceTaskStatus = "pending"
    progress: str | None = None
    message: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None
    report_path: str | None = None
    raw_submit_response: dict[str, Any] | None = None
    raw_status_response: dict[str, Any] | None = None
    raw_result: dict[str, Any] | None = None
    normalized_result: IntelligenceNormalizedResult | None = None
    error: dict[str, Any] | None = None
