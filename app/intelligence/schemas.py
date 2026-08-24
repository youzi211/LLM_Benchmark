from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.models import utc_now

IntelligenceTaskStatus = Literal["pending", "running", "completed", "failed"]


class EvalScopeConfig(BaseModel):
    """Optional local overrides for in-process EvalScope execution.

    Missing config means the built-in defaults are used. Extra keys are ignored so
    old runtime files with removed fields such as ``base_url`` do not break
    startup, but the model no longer exposes or persists those legacy fields.
    """

    model_config = ConfigDict(extra="ignore")

    datasets_dir: str | None = None
    outputs_dir: str | None = None
    # Optional override. When omitted, the runner uses the built-in default Judge
    # selector: the report analysis model configured in data/models.json.
    judge_model_config_id: str | None = None
    judge_generation_config: dict[str, Any] = Field(default_factory=lambda: {"temperature": 0.0, "max_tokens": 4096})
    judge_worker_num: int = Field(default=5, ge=1, le=128)
    ignore_dataset_errors: bool = True
    # EvalScope code-execution benchmarks such as MBPP/MBPP+ require a
    # sandbox during scoring. Keep it disabled by default so non-code
    # evaluations retain the previous minimal zero-config behavior.
    sandbox_enabled: bool = False
    sandbox_type: str = "docker"
    sandbox_manager_config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("datasets_dir", "outputs_dir", "judge_model_config_id", "sandbox_type")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
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
    """Small dataset-level summary used by the UI and overview reports.

    The complete EvalScope dataset report stays in ``IntelligenceTask.raw_result``
    and in EvalScope's output directory.  Do not add raw report/metric payloads
    here: that would make every task persist the same large payload twice.
    """

    dataset: str
    pretty_name: str | None = None
    categories: list[str] = Field(default_factory=list)
    needs_judge: bool | None = None
    score: float | None = None


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
    # Complete in-process EvalScope response.  This is the single canonical
    # business-level archive; normalized_result intentionally remains slim.
    raw_result: dict[str, Any] | None = None
    raw_output_dir: str | None = None
    normalized_result: IntelligenceNormalizedResult | None = None
    error: dict[str, Any] | None = None
