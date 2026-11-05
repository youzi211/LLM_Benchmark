from importlib.metadata import PackageNotFoundError, version
from typing import Any

from app.core.models import ModelConfig
from app.reports.markdown import redact_text


def public_data(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): public_data(v) for k, v in value.items()
                if str(k).lower() not in {"api_key", "key", "secret", "password", "authorization", "access_token", "token", "headers", "api_url", "base_url"}
                and not any(part in str(k).lower() for part in ("password", "secret", "api_key", "authorization"))}
    if isinstance(value, (list, tuple)):
        return [public_data(v) for v in value]
    return redact_text(value) if isinstance(value, str) else value


def execution_snapshot(model: ModelConfig, lane: str, conditions: dict[str, Any]) -> dict[str, Any]:
    try:
        engine_version = version("evalscope") if lane != "basic" else None
    except PackageNotFoundError:
        engine_version = None
    return public_data({"model": {"id": model.id, "name": model.name, "model": model.model,
                                  "protocol": model.protocol, "timeout_seconds": model.timeout_seconds},
                        "lane": lane, "evalscope_version": engine_version,
                        "conditions": conditions})
