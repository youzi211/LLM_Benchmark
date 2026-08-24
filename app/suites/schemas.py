from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import AliasChoices, BaseModel, Field, field_validator, model_validator

from app.core.models import ModelConfig, Protocol, utc_now

SuiteRunStatus = Literal["queued", "running", "completed", "partial", "failed"]
SuiteStepStatus = Literal["pending", "running", "completed", "skipped", "failed"]

# 定时智力评测默认每个数据集只取前 N 条样本，避免 live_code_bench 等大体量数据集磨死整条 suite。
# 手动/quick 评测默认 intelligence_limit=None 不限制；需精确分数时可手动跑全量。
DEFAULT_SCHEDULED_INTELLIGENCE_LIMIT = 200
DEFAULT_SCHEDULE_PROFILE = "scheduled_light"


def new_suite_id() -> str:
    return f"suite_{utc_now().strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:8]}"


def new_schedule_id() -> str:
    return f"suite_schedule_{utc_now().strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:8]}"


def new_inline_model_id() -> str:
    return f"inline_{utc_now().strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:8]}"


def _normalize_base_url(url: str, protocol: Protocol) -> str:
    value = url.rstrip("/")
    suffixes = {
        "chat_completions": "/chat/completions",
        "responses": "/responses",
    }
    suffix = suffixes.get(protocol)
    if suffix and value.endswith(suffix):
        return value[: -len(suffix)].rstrip("/")
    return value


class SuiteStressOptions(BaseModel):
    parallel: list[int] | None = None
    number: list[int] | None = None
    dataset: str | None = None
    dataset_path: str | None = None
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
    intelligence_datasets: list[str] | None = None
    intelligence_limit: int | None = Field(default=None, ge=1)
    intelligence_eval_batch_size: int | None = Field(default=None, ge=1)
    intelligence_generation_config: dict[str, Any] | None = None
    wait_for_completion: bool = False
    poll_interval_seconds: float | None = Field(default=None, ge=0, le=3600)
    timeout_seconds: float | None = Field(default=None, ge=1, le=172800)

    @field_validator("intelligence_datasets")
    @classmethod
    def validate_intelligence_datasets(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = [item.strip() for item in value if item and item.strip()]
        if not cleaned:
            raise ValueError("must not be empty")
        return cleaned

    @model_validator(mode="after")
    def require_at_least_one_component(self) -> "SuiteDefaultRunRequest":
        if not any([self.run_gateway, self.run_intelligence, self.run_stress]):
            raise ValueError("at least one suite component must be enabled")
        return self


class SuiteInlineModelRequest(BaseModel):
    url: str = Field(validation_alias=AliasChoices("url", "base_url"), min_length=1)
    key: str = Field(default="", validation_alias=AliasChoices("key", "api_key"))
    model: str = Field(min_length=1)
    name: str | None = None
    protocol: Protocol = "chat_completions"
    timeout_seconds: int = Field(default=60, ge=1, le=600)
    declared_context_tokens: int | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "declared_context_tokens",
            "context_window_tokens",
            "context_window",
            "max_context_tokens",
        ),
        ge=1,
    )
    declared_max_output_tokens: int | None = Field(
        default=None,
        validation_alias=AliasChoices("declared_max_output_tokens", "max_output_tokens"),
        ge=1,
    )
    concurrency_levels: list[int] = Field(default_factory=lambda: [1, 5, 10, 20])

    @field_validator("url")
    @classmethod
    def strip_url(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("concurrency_levels")
    @classmethod
    def validate_concurrency_levels(cls, value: list[int]) -> list[int]:
        if not value:
            return [1, 5, 10, 20]
        cleaned = sorted(set(value))
        if any(item < 1 or item > 200 for item in cleaned):
            raise ValueError("concurrency levels must be between 1 and 200")
        return cleaned

    def to_model_config(self, model_id: str | None = None) -> ModelConfig:
        resolved_model_id = model_id or new_inline_model_id()
        return ModelConfig(
            id=resolved_model_id,
            name=self.name or f"临时模型 {self.model}",
            protocol=self.protocol,
            base_url=_normalize_base_url(self.url, self.protocol),
            api_key=self.key,
            model=self.model,
            timeout_seconds=self.timeout_seconds,
            enabled=True,
            declared_context_tokens=self.declared_context_tokens,
            declared_max_output_tokens=self.declared_max_output_tokens,
            concurrency_levels=self.concurrency_levels,
        )


class SuiteQuickRunRequest(SuiteInlineModelRequest):
    title: str | None = None
    run_gateway: bool = True
    run_intelligence: bool = True
    run_stress: bool = True
    gateway_plan_id: str = "gateway_acceptance_v1"
    gateway_metric_ids: list[str] | None = None
    stress_options: SuiteStressOptions = Field(default_factory=SuiteStressOptions)
    intelligence_datasets: list[str] | None = None
    intelligence_limit: int | None = Field(default=None, ge=1)
    intelligence_eval_batch_size: int | None = Field(default=None, ge=1)
    intelligence_generation_config: dict[str, Any] | None = None
    wait_for_completion: bool = False
    poll_interval_seconds: float | None = Field(default=None, ge=0, le=3600)
    timeout_seconds_total: float | None = Field(default=None, ge=1, le=172800)

    @field_validator("intelligence_datasets")
    @classmethod
    def validate_intelligence_datasets(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = [item.strip() for item in value if item and item.strip()]
        if not cleaned:
            raise ValueError("must not be empty")
        return cleaned

    @model_validator(mode="after")
    def require_at_least_one_component(self) -> "SuiteQuickRunRequest":
        if not any([self.run_gateway, self.run_intelligence, self.run_stress]):
            raise ValueError("at least one suite component must be enabled")
        return self

    def to_inline_model_config(self) -> ModelConfig:
        return self.to_model_config()

    def to_suite_request(self, model_id: str) -> SuiteDefaultRunRequest:
        return SuiteDefaultRunRequest(
            model_id=model_id,
            title=self.title or f"{self.model} 一键评测",
            run_gateway=self.run_gateway,
            run_intelligence=self.run_intelligence,
            run_stress=self.run_stress,
            gateway_plan_id=self.gateway_plan_id,
            gateway_metric_ids=self.gateway_metric_ids,
            stress_options=self.stress_options,
            intelligence_datasets=self.intelligence_datasets,
            intelligence_limit=self.intelligence_limit,
            intelligence_eval_batch_size=self.intelligence_eval_batch_size,
            intelligence_generation_config=self.intelligence_generation_config,
            wait_for_completion=self.wait_for_completion,
            poll_interval_seconds=self.poll_interval_seconds,
            timeout_seconds=self.timeout_seconds_total,
        )


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
    profile: str | None = DEFAULT_SCHEDULE_PROFILE
    enabled: bool = True
    title: str | None = None
    time_of_day: str = Field(default="02:00", pattern=r"^\d{2}:\d{2}$")
    timezone: str = "Asia/Shanghai"
    interval_days: int = Field(default=1, ge=1, le=365)
    run_once: bool = False
    run_date: date | None = None
    next_run_at: datetime | None = None
    run_gateway: bool = True
    run_intelligence: bool = True
    run_stress: bool = True
    gateway_plan_id: str = "gateway_acceptance_v1"
    gateway_metric_ids: list[str] | None = None
    stress_parallel: list[int] | None = None
    stress_number: list[int] | None = None
    stress_options: SuiteStressOptions = Field(default_factory=SuiteStressOptions)
    intelligence_datasets: list[str] | None = None
    intelligence_limit: int | None = Field(default=None, ge=1)
    intelligence_eval_batch_size: int | None = Field(default=None, ge=1)
    intelligence_generation_config: dict[str, Any] | None = None
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

    @field_validator("intelligence_datasets")
    @classmethod
    def validate_intelligence_datasets(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = [item.strip() for item in value if item and item.strip()]
        if not cleaned:
            raise ValueError("must not be empty")
        return cleaned

    @model_validator(mode="after")
    def validate_run_once_target(self):
        if self.run_once and self.run_date is None and self.next_run_at is None:
            raise ValueError("run_date or next_run_at is required when run_once is true")
        return self

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
            intelligence_datasets=self.intelligence_datasets,
            intelligence_limit=self.intelligence_limit if self.intelligence_limit is not None else DEFAULT_SCHEDULED_INTELLIGENCE_LIMIT,
            intelligence_eval_batch_size=self.intelligence_eval_batch_size,
            intelligence_generation_config=self.intelligence_generation_config,
            wait_for_completion=False,
            poll_interval_seconds=self.poll_interval_seconds,
            timeout_seconds=self.timeout_seconds,
        )


class SuiteSchedule(BaseModel):
    schedule_id: str = Field(default_factory=new_schedule_id)
    name: str
    model_id: str
    profile: str | None = DEFAULT_SCHEDULE_PROFILE
    enabled: bool = True
    title: str | None = None
    time_of_day: str = "02:00"
    timezone: str = "Asia/Shanghai"
    interval_days: int = 1
    run_once: bool = False
    run_date: date | None = None
    request: SuiteDefaultRunRequest
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    next_run_at: datetime
    last_run_at: datetime | None = None
    last_suite_id: str | None = None
    run_count: int = 0
    last_error: dict[str, Any] | None = None


class SuiteScheduleLastRun(BaseModel):
    schedule: SuiteSchedule
    suite: SuiteRun | None = None
    last_suite_status: SuiteRunStatus | None = None
    last_suite_current_step: str | None = None
    last_suite_error_count: int = 0
    last_suite_errors: list[dict[str, Any]] = Field(default_factory=list)
