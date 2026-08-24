from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from typing import Callable

from app.core.models import utc_now
from app.reports.markdown import redact_text
from app.suites.runner import SuiteRunner
from app.suites.store import SuiteScheduleStore, compute_following_run_at

logger = logging.getLogger(__name__)


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
                # 到点投递后台执行即返回，不阻塞调度循环——镜像 /suites/default 路由的
                # background_tasks.add_task 模式，避免单个长 suite 冻结后续所有定时触发。
                task = asyncio.create_task(runner.execute(suite.suite_id))
                task.add_done_callback(
                    _log_background_suite_failure(schedule_id=schedule.schedule_id, suite_id=suite.suite_id)
                )
            except Exception as exc:
                schedule.last_error = {"message": redact_text(str(exc)), "type": exc.__class__.__name__}
            if schedule.run_once:
                schedule.enabled = False
            else:
                schedule.next_run_at = compute_following_run_at(schedule, now=now)
            self.schedule_store.save(schedule)
        return triggered


def _log_background_suite_failure(*, schedule_id: str, suite_id: str):
    def _callback(task: asyncio.Task) -> None:
        try:
            task.result()
        except asyncio.CancelledError:
            logger.info(
                "Scheduled suite background execution was cancelled",
                extra={"schedule_id": schedule_id, "suite_id": suite_id},
            )
        except Exception as exc:  # noqa: BLE001 - callback must never leak to event loop
            logger.exception(
                "Scheduled suite background execution failed: schedule_id=%s suite_id=%s error=%s",
                schedule_id,
                suite_id,
                exc,
            )

    return _callback


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
