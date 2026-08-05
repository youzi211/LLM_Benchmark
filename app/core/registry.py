from __future__ import annotations

from app.core.models import MetricInfo, PlanInfo
from app.core.plans import METRICS, PLANS


def list_metrics() -> list[MetricInfo]:
    return list(METRICS.values())


def get_metric(metric_id: str) -> MetricInfo | None:
    return METRICS.get(metric_id)


def list_plans() -> list[PlanInfo]:
    return list(PLANS.values())


def get_plan(plan_id: str) -> PlanInfo | None:
    return PLANS.get(plan_id)


def resolve_metric_ids(plan_id: str, metric_ids: list[str] | None) -> list[str]:
    if metric_ids is not None:
        for metric_id in metric_ids:
            if metric_id not in METRICS:
                raise ValueError(f"invalid_metric:{metric_id}")
        return metric_ids
    plan = get_plan(plan_id)
    if plan is None:
        raise ValueError(f"invalid_plan:{plan_id}")
    return list(plan.metric_ids)
