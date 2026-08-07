from __future__ import annotations

import asyncio
import os
from datetime import datetime
from typing import Callable

from app.core.models import utc_now
from app.reports.markdown import redact_text
from app.suites.runner import SuiteRunner
from app.suites.store import SuiteScheduleStore, compute_following_run_at


class SuiteScheduler:
    def __init__(
        self,
        *,
        schedule_store: SuiteScheduleStore | None = None,
        suite_runner_factory: Callable[[], SuiteRunner] | None = None,
    ):
        self.schedule_store = schedule_store or SuiteScheduleStore()
        self.suite_runner_factory = suite_runner_factory or SuiteRunner

    async def tick_once(self, now: datetime | None = None) -> int:
        now = now or utc_now()
        triggered = 0
        for schedule in self.schedule_store.due(now):
            try:
                runner = self.suite_runner_factory()
                suite = await runner.start_default(schedule.request, schedule_id=schedule.schedule_id)
                schedule.last_suite_id = suite.suite_id
                schedule.last_run_at = now
                schedule.run_count += 1
                schedule.last_error = None
                triggered += 1
            except Exception as exc:
                schedule.last_error = {"message": redact_text(str(exc)), "type": exc.__class__.__name__}
            if schedule.run_once:
                schedule.enabled = False
            else:
                schedule.next_run_at = compute_following_run_at(schedule, now=now)
            self.schedule_store.save(schedule)
        return triggered


_scheduler_task: asyncio.Task | None = None


async def scheduler_loop(interval_seconds: float | None = None) -> None:
    interval = interval_seconds or float(os.getenv("LLM_BENCHMARK_SCHEDULER_INTERVAL_SECONDS", "60"))
    scheduler = SuiteScheduler()
    while True:
        await scheduler.tick_once()
        await asyncio.sleep(interval)


def start_scheduler() -> None:
    global _scheduler_task
    if os.getenv("LLM_BENCHMARK_SCHEDULER_DISABLED", "0") in {"1", "true", "True"}:
        return
    if _scheduler_task is None or _scheduler_task.done():
        _scheduler_task = asyncio.create_task(scheduler_loop())


def stop_scheduler() -> None:
    global _scheduler_task
    if _scheduler_task is not None and not _scheduler_task.done():
        _scheduler_task.cancel()
    _scheduler_task = None
