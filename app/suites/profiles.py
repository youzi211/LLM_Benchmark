from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.intelligence.config_store import EvalScopeConfigStore
from app.storage.file_utils import read_json_file
from app.suites.schemas import SuiteScheduleCreate, SuiteStressOptions

DEFAULT_SCHEDULE_PROFILE = "scheduled_light"
CODE_EXECUTION_DATASETS = {"humaneval", "humaneval_plus", "mbpp", "mbpp_plus", "live_code_bench"}


class EvalScopeProfile(BaseModel):
    profile_id: str
    name: str
    description: str | None = None
    requires_sandbox: bool = False
    run_gateway: bool | None = None
    run_intelligence: bool | None = None
    run_stress: bool | None = None
    gateway_metric_ids: list[str] | None = None
    intelligence_datasets: list[str] | None = None
    intelligence_limit: int | None = Field(default=None, ge=1)
    intelligence_eval_batch_size: int | None = Field(default=None, ge=1)
    intelligence_generation_config: dict[str, Any] | None = None
    stress_options: SuiteStressOptions = Field(default_factory=SuiteStressOptions)

    @field_validator("intelligence_datasets")
    @classmethod
    def validate_datasets(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = [item.strip() for item in value if item and item.strip()]
        if not cleaned:
            raise ValueError("must not be empty")
        return cleaned


BUILTIN_PROFILES: dict[str, EvalScopeProfile] = {
    "scheduled_light": EvalScopeProfile(
        profile_id="scheduled_light",
        name="定时轻量评测",
        description="默认定时评测 profile：不包含代码执行类数据集，降低 sandbox 依赖与半夜失败概率。",
        requires_sandbox=False,
        run_gateway=True,
        run_intelligence=True,
        run_stress=True,
        intelligence_datasets=["gsm8k", "math_500", "ceval"],
        intelligence_limit=50,
        intelligence_eval_batch_size=5,
        stress_options=SuiteStressOptions(
            dataset="longalpaca",
            parallel=[1, 2, 5],
            number=[10, 20, 50],
            stream=True,
            min_prompt_length=0,
            max_prompt_length=131072,
            min_tokens=128,
            max_tokens=128,
            prefix_length=0,
            extra_args={"ignore_eos": True},
        ),
    ),
    "scheduled_code": EvalScopeProfile(
        profile_id="scheduled_code",
        name="定时代码能力评测",
        description="需要 sandbox 的代码执行类评测 profile，默认只跑 HumanEval/MBPP 小样本。",
        requires_sandbox=True,
        run_gateway=False,
        run_intelligence=True,
        run_stress=False,
        intelligence_datasets=["humaneval", "mbpp"],
        intelligence_limit=20,
        intelligence_eval_batch_size=2,
    ),
    "full_offline": EvalScopeProfile(
        profile_id="full_offline",
        name="完整离线评测",
        description="人工触发的较完整评测 profile，包含代码类数据集，建议确认 sandbox 后使用。",
        requires_sandbox=True,
        run_gateway=True,
        run_intelligence=True,
        run_stress=True,
        intelligence_datasets=[
            "humaneval",
            "mbpp",
            "humaneval_plus",
            "mbpp_plus",
            "live_code_bench",
            "gsm8k",
            "math_500",
            "mmlu_pro",
            "ceval",
            "bbh",
        ],
        intelligence_limit=None,
        intelligence_eval_batch_size=5,
        stress_options=SuiteStressOptions(dataset="longalpaca", parallel=[1, 5], number=[10, 50], stream=True),
    ),
}


class EvalScopeProfileStore:
    def __init__(self, path: Path | None = None):
        self.path = path or (Path(os.getenv("LLM_BENCHMARK_DATA_DIR", "data")) / "evalscope_profiles.json")

    def list(self) -> list[EvalScopeProfile]:
        profiles = dict(BUILTIN_PROFILES)
        data = read_json_file(self.path, {})
        raw_profiles = data.get("profiles", {}) if isinstance(data, dict) else {}
        if isinstance(raw_profiles, dict):
            for profile_id, raw in raw_profiles.items():
                if not isinstance(raw, dict):
                    continue
                payload = {**raw, "profile_id": raw.get("profile_id", profile_id)}
                profiles[payload["profile_id"]] = EvalScopeProfile.model_validate(payload)
        elif isinstance(raw_profiles, list):
            for raw in raw_profiles:
                if isinstance(raw, dict):
                    profile = EvalScopeProfile.model_validate(raw)
                    profiles[profile.profile_id] = profile
        return sorted(profiles.values(), key=lambda item: item.profile_id)

    def get(self, profile_id: str) -> EvalScopeProfile | None:
        return next((item for item in self.list() if item.profile_id == profile_id), None)


def apply_profile_to_schedule_request(
    request: SuiteScheduleCreate,
    *,
    profile_store: EvalScopeProfileStore | None = None,
    config_store: EvalScopeConfigStore | None = None,
) -> SuiteScheduleCreate:
    if request.profile is None:
        return request
    store = profile_store or EvalScopeProfileStore()
    profile = store.get(request.profile)
    if profile is None:
        raise ValueError(f"profile_not_found:{request.profile}")

    profile_datasets = set(profile.intelligence_datasets or [])
    needs_sandbox = profile.requires_sandbox or bool(profile_datasets & CODE_EXECUTION_DATASETS)
    config = (config_store or EvalScopeConfigStore()).load()
    if needs_sandbox and not config.sandbox_enabled:
        raise ValueError(f"profile_requires_sandbox:{profile.profile_id}")

    explicit = request.model_fields_set
    updates: dict[str, Any] = {"profile": profile.profile_id}
    for name in ("run_gateway", "run_intelligence", "run_stress", "gateway_metric_ids"):
        value = getattr(profile, name)
        if name not in explicit and value is not None:
            updates[name] = value
    for name in (
        "intelligence_datasets",
        "intelligence_limit",
        "intelligence_eval_batch_size",
        "intelligence_generation_config",
    ):
        value = getattr(profile, name)
        if name not in explicit and value is not None:
            updates[name] = value

    stress_options = request.stress_options.model_copy(deep=True)
    stress_explicit = request.stress_options.model_fields_set if "stress_options" in explicit else set()
    profile_stress = profile.stress_options
    for field_name in SuiteStressOptions.model_fields:
        value = getattr(profile_stress, field_name)
        if value is not None and field_name not in stress_explicit:
            setattr(stress_options, field_name, value)
    updates["stress_options"] = stress_options

    return request.model_copy(update=updates)
