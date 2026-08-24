from __future__ import annotations

import asyncio

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
