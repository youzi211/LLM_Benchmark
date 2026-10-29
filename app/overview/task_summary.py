from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from app.storage.intelligence_task_store import IntelligenceTaskStore
from app.storage.stress_task_store import StressTaskStore
from app.storage.task_store import TaskStore

FINAL_STATUSES = {"completed", "partial", "failed", "interrupted", "error"}
SUMMARY_TIMEZONE = ZoneInfo("Asia/Shanghai")


class TaskOverviewSummary(BaseModel):
    today_count: int
    final_count: int
    completed_count: int
    completion_rate: float | None
    avg_duration_ms: int | None


def _timestamp(task: Any) -> datetime | None:
    for field in ("started_at", "created_at", "updated_at"):
        value = getattr(task, field, None)
        if isinstance(value, datetime):
            return value
    return None


def _summary_now(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(SUMMARY_TIMEZONE)
    if now.tzinfo is None:
        return now.replace(tzinfo=SUMMARY_TIMEZONE)
    return now.astimezone(SUMMARY_TIMEZONE)


def _is_today(timestamp: datetime, local_now: datetime) -> bool:
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    return timestamp.astimezone(SUMMARY_TIMEZONE).date() == local_now.date()


def _positive_duration(task: Any) -> float | None:
    value = getattr(task, "duration_ms", None)
    if value is None:
        return None
    duration = float(value)
    return duration if math.isfinite(duration) and duration > 0 else None


def build_task_overview_summary(
    *,
    task_store: TaskStore | None = None,
    stress_store: StressTaskStore | None = None,
    intelligence_store: IntelligenceTaskStore | None = None,
    now: datetime | None = None,
) -> TaskOverviewSummary:
    task_store = task_store or TaskStore()
    stress_store = stress_store or StressTaskStore()
    intelligence_store = intelligence_store or IntelligenceTaskStore()
    local_now = _summary_now(now)
    today_count = 0
    final_count = 0
    completed_count = 0
    duration_sum = 0.0
    duration_count = 0

    for store in (task_store, stress_store, intelligence_store):
        for task in store.iter_tasks():
            timestamp = _timestamp(task)
            if timestamp is not None and _is_today(timestamp, local_now):
                today_count += 1
            if str(getattr(task, "status", "")) in FINAL_STATUSES:
                final_count += 1
                if getattr(task, "status", None) == "completed":
                    completed_count += 1
            if (duration := _positive_duration(task)) is not None:
                duration_sum += duration
                duration_count += 1

    return TaskOverviewSummary(
        today_count=today_count,
        final_count=final_count,
        completed_count=completed_count,
        completion_rate=round(completed_count / final_count * 100, 1) if final_count else None,
        avg_duration_ms=round(duration_sum / duration_count) if duration_count else None,
    )
