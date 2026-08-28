from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from numbers import Real
from typing import Any


def make_json_safe(value: Any) -> Any:
    """Return a recursively JSON-safe copy of ``value``.

    EvalScope may produce NaN/Infinity in percentile and throughput metrics when
    a tiny or failed run has insufficient samples. Python's ``json`` module can
    persist those values, but Starlette emits strict JSON and rejects them at API
    response time. Convert non-finite numeric values to ``None`` so historical
    task payloads remain readable by clients.
    """

    if hasattr(value, "model_dump"):
        try:
            return make_json_safe(value.model_dump(mode="json"))
        except TypeError:
            return make_json_safe(value.model_dump())
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Real) and not isinstance(value, bool):
        try:
            numeric = float(value)
        except (TypeError, ValueError, OverflowError):
            return value
        return value if math.isfinite(numeric) else None
    if isinstance(value, Mapping):
        return {str(key): make_json_safe(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [make_json_safe(item) for item in value]
    if isinstance(value, list):
        return [make_json_safe(item) for item in value]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [make_json_safe(item) for item in value]
    return value
