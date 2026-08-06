from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.models import utc_now

SuiteRunStatus = Literal["queued", "running", "completed", "partial", "failed"]
SuiteStepStatus = Literal["pending", "running", "completed", "skipped", "failed"]


def new_suite_id() -> str:
    return f"suite_{utc_now().strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:8]}"


def new_schedule_id() -> str:
    return f"suite_schedule_{utc_now().strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:8]}"


class SuiteStressOptions(BaseModel):
    parallel: list[int] | None = None
    number: list[int] | None = None
    dataset: str | None = None
    stream: bool | None = None
    min_prompt_length: int | None = Field(default=None, ge=0)
    max_prompt_length: int | None = Field(default=None, ge=1)
    min_tokens: int | None = Field(default=None, ge=1)
    max_tokens: int | None = Field(default=None, ge=1)
    rate: float | None = None
    tokenizer_path: str | None = None
    prefix_length: int | None = Field(default=None, ge=0)
    dataset_args: dict[str, Any] | None = None
    extra_args: dict[str, Any] | None = None

    @field_validator("parallel", "number")
    @classmethod
    def validate_positive_lists(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return None
        if not value:
            raise ValueError("must not be empty")
        if any(item < 1 for item in value):
            raise ValueError("values must be positive")
        return value

    def to_stress_request_data(self, model_id: str) -> dict[str, Any]:
        data = self.model_dump(exclude_none=True)
        data["model_id"] = model_id
        return data


class SuiteDefaultRunRequest(BaseModel):
    model_id: str
    title: str | None = None
    run_gateway: bool = True
    run_intelligence: bool = True
    run_stress: bool = True
    gateway_plan_id: str = "gateway_acceptance_v1"
    gateway_metric_ids: list[str] | None = None
    stress_options: SuiteStressOptions = Field(default_factory=SuiteStressOptions)
    wait_for_completion: bool = False
    poll_interval_seconds: float | None = Field(default=None, ge=0, le=3600)
    timeout_seconds: float | None = Field(default=None, ge=1, le=172800)

    @model_validator(mode="after")
    def require_at_least_one_component(self) -> "SuiteDefaultRunRequest":
        if not any([self.run_gateway, self.run_intelligence, self.run_stress]):
            raise ValueError("at least one suite component must be enabled")
        return self


class SuiteStep(BaseModel):
    name: str
    title: str
    enabled: bool = True
    status: SuiteStepStatus = "pending"
    task_id: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    message: str | None = None


class SuiteRun(BaseModel):
    suite_id: str = Field(default_factory=new_suite_id)
    model_id: str
    title: str | None = None
    status: SuiteRunStatus = "queued"
    current_step: str | None = None
    request: SuiteDefaultRunRequest
    schedule_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    gateway_task_id: str | None = None
    intelligence_task_id: str | None = None
    stress_task_id: str | None = None
    overview_id: str | None = None
    overview_report_path: str | None = None
    steps: list[SuiteStep] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)


class SuiteScheduleCreate(BaseModel):
    name: str
    model_id: str
    enabled: bool = True
    title: str | None = None
    time_of_day: str = Field(default="02:00", pattern=r"^\d{2}:\d{2}$")
    timezone: str = "Asia/Shanghai"
    interval_days: int = Field(default=1, ge=1, le=365)
    next_run_at: datetime | None = None
    run_gateway: bool = True
    run_intelligence: bool = True
    run_stress: bool = True
    gateway_plan_id: str = "gateway_acceptance_v1"
    gateway_metric_ids: list[str] | None = None
    stress_parallel: list[int] | None = None
    stress_number: list[int] | None = None
    stress_options: SuiteStressOptions = Field(default_factory=SuiteStressOptions)
    poll_interval_seconds: float | None = Field(default=None, ge=0, le=3600)
    timeout_seconds: float | None = Field(default=None, ge=1, le=172800)

    @field_validator("stress_parallel", "stress_number")
    @classmethod
    def validate_positive_lists(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return None
        if not value:
            raise ValueError("must not be empty")
        if any(item < 1 for item in value):
            raise ValueError("values must be positive")
        return value

    def to_run_request(self) -> SuiteDefaultRunRequest:
        stress_options = self.stress_options.model_copy(deep=True)
        if self.stress_parallel is not None:
            stress_options.parallel = self.stress_parallel
        if self.stress_number is not None:
            stress_options.number = self.stress_number
        return SuiteDefaultRunRequest(
            model_id=self.model_id,
            title=self.title or self.name,
            run_gateway=self.run_gateway,
            run_intelligence=self.run_intelligence,
            run_stress=self.run_stress,
            gateway_plan_id=self.gateway_plan_id,
            gateway_metric_ids=self.gateway_metric_ids,
            stress_options=stress_options,
            wait_for_completion=True,
            poll_interval_seconds=self.poll_interval_seconds,
            timeout_seconds=self.timeout_seconds,
        )


class SuiteSchedule(BaseModel):
    schedule_id: str = Field(default_factory=new_schedule_id)
    name: str
    model_id: str
    enabled: bool = True
    title: str | None = None
    time_of_day: str = "02:00"
    timezone: str = "Asia/Shanghai"
    interval_days: int = 1
    request: SuiteDefaultRunRequest
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    next_run_at: datetime
    last_run_at: datetime | None = None
    last_suite_id: str | None = None
    run_count: int = 0
    last_error: dict[str, Any] | None = None
