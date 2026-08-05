from __future__ import annotations

from fastapi import APIRouter

from app.api.errors import api_error
from app.core.registry import get_plan, list_metrics, list_plans

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
def get_metrics():
    return list_metrics()


@router.get("/plans")
def get_plans():
    return list_plans()


@router.get("/plans/{plan_id}")
def get_plan_by_id(plan_id: str):
    plan = get_plan(plan_id)
    if plan is None:
        raise api_error(404, "plan_not_found", f"Plan not found: {plan_id}")
    return plan
