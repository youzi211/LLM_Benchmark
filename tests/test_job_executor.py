from __future__ import annotations

import asyncio
import threading
import time

import pytest

from app.jobs.executor import JobExecutor
from app.jobs.store import JobStore


@pytest.mark.asyncio
async def test_job_executor_runs_sync_job_and_persists_status(tmp_path):
    store = JobStore(tmp_path / "jobs")
    executor = JobExecutor(store=store, max_concurrency=1)

    job = executor.submit_sync(
        job_type="suite",
        target_id="suite_demo",
        payload={"suite_id": "suite_demo"},
        func=lambda: "ok",
    )
    finished = await executor.wait(job.job_id, timeout=5)

    assert finished is not None
    assert finished.status == "completed"
    assert finished.job_type == "suite"
    assert finished.target_id == "suite_demo"
    assert finished.started_at is not None
    assert finished.completed_at is not None
    assert store.get(job.job_id).status == "completed"


@pytest.mark.asyncio
async def test_job_executor_records_failures(tmp_path):
    store = JobStore(tmp_path / "jobs")
    executor = JobExecutor(store=store, max_concurrency=1)

    def explode():
        raise RuntimeError("boom")

    job = executor.submit_sync(job_type="stress", target_id="stress_demo", payload={}, func=explode)
    finished = await executor.wait(job.job_id, timeout=5)

    assert finished is not None
    assert finished.status == "failed"
    assert finished.error == {"message": "boom", "type": "RuntimeError"}


@pytest.mark.asyncio
async def test_job_executor_limits_concurrency(tmp_path):
    store = JobStore(tmp_path / "jobs")
    executor = JobExecutor(store=store, max_concurrency=1)
    events: list[str] = []

    def make_job(name: str):
        def _run():
            events.append(f"start:{name}")
            import time
            time.sleep(0.05)
            events.append(f"end:{name}")
        return _run

    first = executor.submit_sync(job_type="suite", target_id="suite1", payload={}, func=make_job("one"))
    second = executor.submit_sync(job_type="suite", target_id="suite2", payload={}, func=make_job("two"))

    await executor.wait(first.job_id, timeout=5)
    await executor.wait(second.job_id, timeout=5)

    assert events == ["start:one", "end:one", "start:two", "end:two"]


@pytest.mark.asyncio
async def test_job_executor_cancel_running_sync_job_marks_interrupted(tmp_path):
    store = JobStore(tmp_path / "jobs")
    executor = JobExecutor(store=store, max_concurrency=1)
    started = threading.Event()
    release = threading.Event()

    def slow_job():
        started.set()
        release.wait(timeout=1)

    job = executor.submit_sync(job_type="intelligence", target_id="intel_demo", payload={}, func=slow_job)
    assert await asyncio.to_thread(started.wait, 1)

    cancelled = await executor.cancel(job.job_id)

    assert cancelled is not None
    assert cancelled.status == "interrupted"
    assert store.get(job.job_id).status == "interrupted"
    release.set()
    finished = await executor.wait(job.job_id, timeout=1)
    assert finished is not None
    assert finished.status == "interrupted"


@pytest.mark.asyncio
async def test_job_executor_cancel_queued_job_is_idempotent(tmp_path):
    store = JobStore(tmp_path / "jobs")
    executor = JobExecutor(store=store, max_concurrency=1)
    started = asyncio.Event()
    release = asyncio.Event()
    ran_second = False

    async def blocking_job():
        started.set()
        await release.wait()

    async def second_job():
        nonlocal ran_second
        ran_second = True

    first = executor.submit_async(job_type="suite", target_id="suite_one", payload={}, func=blocking_job)
    await started.wait()
    second = executor.submit_async(job_type="suite", target_id="suite_two", payload={}, func=second_job)
    assert store.get(second.job_id).status == "queued"

    cancelled = await executor.cancel(second.job_id)
    cancelled_again = await executor.cancel(second.job_id)

    assert cancelled is not None
    assert cancelled.status == "interrupted"
    assert cancelled_again is not None
    assert cancelled_again.status == "interrupted"
    release.set()
    await executor.wait(first.job_id, timeout=1)
    second_record = await executor.wait(second.job_id, timeout=1)
    assert second_record is not None
    assert second_record.status == "interrupted"
    assert ran_second is False
