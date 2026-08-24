from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable
from typing import Any, TypeVar

from app.core.models import utc_now
from app.jobs.schemas import JobRecord, JobType
from app.jobs.store import JobStore
from app.reports.markdown import redact_text

T = TypeVar("T")
logger = logging.getLogger(__name__)


class JobExecutor:
    def __init__(self, *, store: JobStore | None = None, max_concurrency: int | None = None):
        self.store = store or JobStore()
        default_max = max_concurrency or int(os.getenv("LLM_BENCHMARK_JOB_MAX_CONCURRENCY", "2"))
        self.max_concurrency = default_max
        self.suite_max_concurrency = int(os.getenv("LLM_BENCHMARK_SUITE_JOB_MAX_CONCURRENCY", str(default_max)))
        self.evalscope_max_concurrency = int(os.getenv("LLM_BENCHMARK_EVALSCOPE_JOB_MAX_CONCURRENCY", str(default_max)))
        self._suite_semaphore = asyncio.Semaphore(self.suite_max_concurrency)
        self._evalscope_semaphore = asyncio.Semaphore(self.evalscope_max_concurrency)
        self._tasks: dict[str, asyncio.Task] = {}

    def submit_sync(self, *, job_type: JobType, target_id: str | None, payload: dict[str, Any], func: Callable[[], T]) -> JobRecord:
        job = self.store.save(JobRecord(job_type=job_type, target_id=target_id, payload=payload))
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return self._run_sync_without_loop(job, func)
        task = loop.create_task(self._run_job(job.job_id, lambda: asyncio.to_thread(func)))
        self._tasks[job.job_id] = task
        return job

    def submit_async(self, *, job_type: JobType, target_id: str | None, payload: dict[str, Any], func: Callable[[], Any]) -> JobRecord:
        job = self.store.save(JobRecord(job_type=job_type, target_id=target_id, payload=payload))
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(self._run_job(job.job_id, func))
            return self.store.get(job.job_id) or job
        task = loop.create_task(self._run_job(job.job_id, func))
        self._tasks[job.job_id] = task
        return job

    def _semaphore_for(self, job_type: JobType) -> asyncio.Semaphore:
        if job_type == "suite":
            return self._suite_semaphore
        return self._evalscope_semaphore

    def _run_sync_without_loop(self, job: JobRecord, func: Callable[[], T]) -> JobRecord:
        async def _runner() -> JobRecord:
            await self._run_job(job.job_id, lambda: asyncio.to_thread(func))
            return self.store.get(job.job_id) or job

        return asyncio.run(_runner())

    async def _run_job(self, job_id: str, func: Callable[[], Any]) -> None:
        first_job = self.store.get(job_id)
        if first_job is None:
            return
        async with self._semaphore_for(first_job.job_type):
            job = self.store.get(job_id)
            if job is None:
                return
            job.status = "running"
            job.started_at = job.started_at or utc_now()
            job.error = None
            self.store.save(job)
            try:
                result = func()
                if asyncio.iscoroutine(result) or isinstance(result, asyncio.Future):
                    await result
                job = self.store.get(job_id) or job
                job.status = "completed"
                job.completed_at = utc_now()
                job.error = None
                self.store.save(job)
            except asyncio.CancelledError:
                job = self.store.get(job_id) or job
                job.status = "interrupted"
                job.completed_at = utc_now()
                job.error = {"message": "job cancelled", "type": "CancelledError"}
                self.store.save(job)
                logger.info("Job interrupted: job_id=%s job_type=%s target_id=%s", job.job_id, job.job_type, job.target_id)
                raise
            except Exception as exc:  # noqa: BLE001 - job boundary records any failure
                job = self.store.get(job_id) or job
                job.status = "failed"
                job.completed_at = utc_now()
                job.error = {"message": redact_text(str(exc)), "type": exc.__class__.__name__}
                self.store.save(job)
                logger.exception("Job failed: job_id=%s job_type=%s target_id=%s", job.job_id, job.job_type, job.target_id)

    async def wait(self, job_id: str, timeout: float | None = None) -> JobRecord | None:
        task = self._tasks.get(job_id)
        if task is not None:
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
            except asyncio.TimeoutError:
                return self.store.get(job_id)
        return self.store.get(job_id)

    async def shutdown(self, timeout: float = 5.0) -> None:
        pending = [task for task in self._tasks.values() if not task.done()]
        if not pending:
            return
        done, still_pending = await asyncio.wait(pending, timeout=timeout)
        for task in done:
            try:
                task.result()
            except Exception:  # noqa: BLE001 - already captured by _run_job when possible
                pass
        for task in still_pending:
            task.cancel()
        for job in self.store.list(limit=1000):
            if job.status in {"queued", "running"}:
                job.status = "interrupted"
                job.completed_at = utc_now()
                job.error = {"message": "job interrupted during application shutdown", "type": "Interrupted"}
                self.store.save(job)


_job_executor: JobExecutor | None = None


def get_job_executor() -> JobExecutor:
    global _job_executor
    if _job_executor is None:
        _job_executor = JobExecutor()
    return _job_executor


def reset_job_executor() -> None:
    global _job_executor
    _job_executor = None


async def shutdown_job_executor(timeout: float | None = None) -> None:
    if _job_executor is None:
        return
    await _job_executor.shutdown(timeout or float(os.getenv("LLM_BENCHMARK_JOB_SHUTDOWN_TIMEOUT_SECONDS", "5")))
