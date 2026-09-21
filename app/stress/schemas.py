from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.models import utc_now
from app.evalscope_defaults import (
    DEFAULT_STRESS_DATASET,
    DEFAULT_STRESS_MAX_PROMPT_LENGTH,
    DEFAULT_STRESS_MAX_TOKENS,
    DEFAULT_STRESS_MIN_PROMPT_LENGTH,
    DEFAULT_STRESS_NUMBER,
    DEFAULT_STRESS_PARALLEL,
    DEFAULT_STRESS_PREFIX_LENGTH,
    DEFAULT_STRESS_RATE,
    DEFAULT_STRESS_STREAM,
)

StressTaskStatus = Literal["pending", "running", "completed", "failed", "interrupted"]
RateValue = float | list[float]
TokenLimit = int | list[int]


def validate_closed_loop_sweep_lengths(parallel: list[int] | None, number: list[int] | None) -> None:
    """EvalScope perf pairs ``parallel`` and ``number`` by position in closed-loop mode."""
    if parallel is not None and number is not None and len(parallel) != len(number):
        raise ValueError(
            "parallel and number must have the same length for EvalScope closed-loop stress sweeps "
            f"(got parallel={len(parallel)}, number={len(number)})"
        )


def validate_open_loop_sweep_lengths(rate: RateValue | None, number: list[int] | None) -> None:
    """EvalScope perf pairs list-valued ``rate`` and ``number`` in open-loop mode."""
    if isinstance(rate, list) and number is not None and len(rate) != len(number):
        raise ValueError(
            "rate and number must have the same length for EvalScope open-loop stress sweeps "
            f"(got rate={len(rate)}, number={len(number)})"
        )


class StressDefaultRunRequest(BaseModel):
    model_id: str
    parallel: list[int] | None = None
    number: list[int] | None = None
    dataset: str | None = None
    dataset_path: str | None = None
    stream: bool | None = None
    min_prompt_length: int | None = Field(default=None, ge=0)
    max_prompt_length: int | None = Field(default=None, ge=1)
    min_tokens: int | None = Field(default=None, ge=1)
    max_tokens: TokenLimit | None = None
    rate: RateValue | None = None
    tokenizer_path: str | None = None
    prefix_length: int | None = Field(default=None, ge=0)
    dataset_args: dict[str, Any] | None = None
    extra_args: dict[str, Any] | None = None
    data_source: Literal["modelscope", "huggingface", "local"] | None = None
    open_loop: bool = False
    warmup_num: float | None = Field(default=None, ge=0)
    duration: float | None = Field(default=None, gt=0)
    multi_turn: bool = False
    min_turns: int | None = Field(default=None, ge=1)
    max_turns: int | None = Field(default=None, ge=1)
    connect_timeout: int | None = Field(default=None, ge=1)
    read_timeout: int | None = Field(default=None, ge=1)
    total_timeout: int | None = Field(default=None, ge=1)
    temperature: float | None = Field(default=None, ge=0)
    top_p: float | None = Field(default=None, ge=0, le=1)
    top_k: int | None = Field(default=None, ge=1)
    frequency_penalty: float | None = None
    repetition_penalty: float | None = Field(default=None, gt=0)
    logprobs: bool | None = None
    n_choices: int | None = Field(default=None, ge=1)
    seed: int | None = None
    stop: list[str] | None = None
    stop_token_ids: list[str] | None = None
    tokenize_prompt: bool | None = None

    @model_validator(mode="after")
    def validate_sweep_lengths(self) -> "StressDefaultRunRequest":
        if self.open_loop:
            validate_open_loop_sweep_lengths(self.rate, self.number)
        else:
            validate_closed_loop_sweep_lengths(self.parallel, self.number)
        if self.min_turns is not None and self.max_turns is not None and self.min_turns > self.max_turns:
            raise ValueError("min_turns must be less than or equal to max_turns")
        if self.dataset and "multi_turn" in self.dataset and not self.multi_turn:
            raise ValueError("multi_turn must be enabled for a multi-turn dataset")
        return self


class StressRunRequest(StressDefaultRunRequest):
    pass


class StressRemoteSubmitPayload(BaseModel):
    model: str
    url: str
    api_key: str = "EMPTY"
    api: str = "openai"
    parallel: list[int] = Field(default_factory=lambda: list(DEFAULT_STRESS_PARALLEL))
    number: list[int] = Field(default_factory=lambda: list(DEFAULT_STRESS_NUMBER))
    dataset: str = DEFAULT_STRESS_DATASET
    dataset_path: str | None = None
    stream: bool = DEFAULT_STRESS_STREAM
    # 长度与 tokenizer 默认值对齐 EvalScope 官方默认（见 parameters 文档 Prompt 设置）：
    # min_prompt_length=0、max_prompt_length=131072、tokenizer_path=None。
    # tokenizer_path=None 时 EvalScope 按字符长度过滤，正好适配 longalpaca 这类
    # 真实长文本语料；原先 1024 token + Qwen tokenizer 的过滤会把长文本几乎全部丢弃。
    min_prompt_length: int = Field(default=DEFAULT_STRESS_MIN_PROMPT_LENGTH, ge=0)
    max_prompt_length: int = Field(default=DEFAULT_STRESS_MAX_PROMPT_LENGTH, ge=1)
    min_tokens: int | None = Field(default=None, ge=1)
    max_tokens: TokenLimit = DEFAULT_STRESS_MAX_TOKENS
    rate: RateValue = DEFAULT_STRESS_RATE
    tokenizer_path: str | None = None
    prefix_length: int = Field(default=DEFAULT_STRESS_PREFIX_LENGTH, ge=0)
    dataset_args: dict[str, Any] = Field(default_factory=dict)
    extra_args: dict[str, Any] = Field(default_factory=dict)
    data_source: Literal["modelscope", "huggingface", "local"] | None = None
    open_loop: bool = False
    warmup_num: float = Field(default=0, ge=0)
    duration: float | None = Field(default=None, gt=0)
    multi_turn: bool = False
    min_turns: int = Field(default=1, ge=1)
    max_turns: int | None = Field(default=None, ge=1)
    connect_timeout: int | None = Field(default=None, ge=1)
    read_timeout: int | None = Field(default=None, ge=1)
    total_timeout: int | None = Field(default=None, ge=1)
    temperature: float | None = Field(default=None, ge=0)
    top_p: float | None = Field(default=None, ge=0, le=1)
    top_k: int | None = Field(default=None, ge=1)
    frequency_penalty: float | None = None
    repetition_penalty: float | None = Field(default=None, gt=0)
    logprobs: bool | None = None
    n_choices: int | None = Field(default=None, ge=1)
    seed: int | None = None
    stop: list[str] | None = None
    stop_token_ids: list[str] | None = None
    tokenize_prompt: bool = False

    @field_validator("parallel", "number")
    @classmethod
    def require_non_empty_positive(cls, value: list[int]) -> list[int]:
        if not value:
            raise ValueError("must not be empty")
        if any(item < 1 for item in value):
            raise ValueError("values must be positive")
        return value

    @model_validator(mode="after")
    def validate_sweep_lengths(self) -> "StressRemoteSubmitPayload":
        if self.open_loop:
            validate_open_loop_sweep_lengths(self.rate, self.number)
        else:
            validate_closed_loop_sweep_lengths(self.parallel, self.number)
        if self.max_turns is not None and self.min_turns > self.max_turns:
            raise ValueError("min_turns must be less than or equal to max_turns")
        return self


class StressRunResult(BaseModel):
    parallel: int | None = None
    rate: float | None = None
    number: int | None = None
    total: int | None = None
    success: int | None = None
    failed: int | None = None
    success_rate: float | None = None
    request_throughput: float | None = None
    output_throughput: float | None = None
    total_throughput: float | None = None
    avg_latency_seconds: float | None = None
    p50_latency_seconds: float | None = None
    p95_latency_seconds: float | None = None
    p99_latency_seconds: float | None = None
    avg_ttft_ms: float | None = None
    p95_ttft_ms: float | None = None
    p99_ttft_ms: float | None = None
    avg_tpot_ms: float | None = None
    p95_tpot_ms: float | None = None
    p99_tpot_ms: float | None = None
    avg_itl_ms: float | None = None
    avg_input_tokens: float | None = None
    avg_output_tokens: float | None = None
    input_throughput: float | None = None
    avg_turns: float | None = None
    avg_cached_percent: float | None = None
    avg_first_turn_ttft_ms: float | None = None
    avg_subsequent_turn_ttft_ms: float | None = None
    trace_summary: dict[str, Any] | None = None


class StressProgress(BaseModel):
    status: str = "running"
    pipeline: str | None = None
    total_requests: int | None = None
    completed_requests: int | None = None
    success_requests: int | None = None
    failed_requests: int | None = None
    current_run: int | None = None
    total_runs: int | None = None
    current_run_completed: int | None = None
    current_run_total: int | None = None
    percent: float | None = Field(default=None, ge=0, le=100)
    updated_at: datetime | None = None


class StressNormalizedResult(BaseModel):
    task_id: str
    evalscope_stress_task_id: str | None = None
    model: str | None = None
    status: str | None = None
    summary: dict[str, Any] = Field(default_factory=dict)
    runs: list[StressRunResult] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)


class StressTask(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    task_id: str
    evalscope_stress_task_id: str | None = None
    model_id: str
    model_config_name: str | None = None
    upstream_model_name: str | None = None
    protocol: str | None = None
    evalscope_base_url: str
    status: StressTaskStatus = "pending"
    progress: str | None = None
    progress_detail: StressProgress | None = None
    message: str | None = None
    request_config: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None
    report_path: str | None = None
    raw_submit_response: dict[str, Any] | None = None
    raw_status_response: dict[str, Any] | None = None
    # Complete in-process EvalScope response.  This is the single canonical
    # business-level archive; normalized_result contains only UI summaries.
    raw_result: dict[str, Any] | None = None
    raw_output_dir: str | None = None
    normalized_result: StressNormalizedResult | None = None
    error: dict[str, Any] | None = None
