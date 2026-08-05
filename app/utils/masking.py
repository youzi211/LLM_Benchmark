from __future__ import annotations

from app.core.models import ModelConfig, ModelConfigPublic


def mask_secret(value: str | None) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def mask_model_config(config: ModelConfig) -> ModelConfigPublic:
    return ModelConfigPublic(**{**config.model_dump(), "api_key": mask_secret(config.api_key)})
