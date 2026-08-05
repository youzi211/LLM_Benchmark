from __future__ import annotations

from app.core.models import MetricResult
from app.core.plans import get_metric_name


def completed(metric_id: str, summary: str, observations: dict) -> MetricResult:
    return MetricResult(
        metric_id=metric_id,
        metric_name=get_metric_name(metric_id),
        status="completed",
        summary=summary,
        observations=observations,
    )


def errored(metric_id: str, summary: str, observations: dict, errors: list[dict]) -> MetricResult:
    return MetricResult(
        metric_id=metric_id,
        metric_name=get_metric_name(metric_id),
        status="error",
        summary=summary,
        observations=observations,
        errors=errors,
    )


def skipped(metric_id: str, summary: str, observations: dict | None = None) -> MetricResult:
    return MetricResult(
        metric_id=metric_id,
        metric_name=get_metric_name(metric_id),
        status="skipped",
        summary=summary,
        observations=observations or {},
    )
