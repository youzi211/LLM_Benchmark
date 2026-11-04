import asyncio
import threading

import pytest

from app.jobs.executor import JobExecutor
from app.jobs.store import JobStore
from app.jobs.schemas import JobRecord
from app.jobs.recovery import reconcile_startup
from app.storage.file_utils import save_record


@pytest.mark.asyncio
async def test_cancelled_thread_keeps_evalscope_slot(tmp_path):
    executor = JobExecutor(store=JobStore(tmp_path), max_concurrency=1)
    entered, release, second = threading.Event(), threading.Event(), threading.Event()
    def work():
        entered.set()
        release.wait(5)
    first = executor.submit_sync(job_type="stress", target_id="one", payload={}, func=work)
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        cancelled = await executor.cancel(first.job_id)
        assert cancelled.status == "running"
        assert cancelled.cancel_requested_at is not None
        other = executor.submit_sync(job_type="intelligence", target_id="two", payload={}, func=second.set)
        await asyncio.sleep(.05)
        assert not second.is_set()
    finally:
        release.set()
        await executor.wait(first.job_id, timeout=3)
    assert executor.store.get(first.job_id).status == "interrupted"
    await executor.wait(other.job_id, timeout=3)
    assert second.is_set()


@pytest.mark.asyncio
async def test_queued_cancel_does_not_start_worker(tmp_path):
    executor = JobExecutor(store=JobStore(tmp_path), max_concurrency=1)
    release = asyncio.Event()
    first = executor.submit_async(job_type="stress", target_id="one", payload={}, func=release.wait)
    await asyncio.sleep(0)
    called = []
    job = executor.submit_sync(job_type="stress", target_id="two", payload={}, func=lambda: called.append(True))
    assert (await executor.cancel(job.job_id)).status == "interrupted"
    release.set()
    await executor.wait(first.job_id, timeout=2)
    await executor.wait(job.job_id, timeout=2)
    assert not called


def test_startup_interrupts_stale_work_without_replay(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_BENCHMARK_DATA_DIR", str(tmp_path))
    store = JobStore()
    job = store.save(JobRecord(job_type="stress", status="running"))
    reconcile_startup()
    recovered = store.get(job.job_id)
    assert recovered.status == "interrupted"
    assert recovered.completed_at is not None
    assert recovered.error["type"] == "ProcessRestart"
    assert len(store.list(limit=None)) == 1


def test_late_worker_cannot_revert_terminal_state(tmp_path):
    store = JobStore(tmp_path)
    job = store.save(JobRecord(job_type="stress", status="running"))
    stale = job.model_copy()
    job.status = "interrupted"
    store.save(job)
    stale.status = "completed"
    assert store.save(stale).status == "interrupted"
    assert store.get(job.job_id).status == "interrupted"


def test_parallel_model_updates_share_lock_and_leave_valid_json(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from app.core.models import ModelConfigCreate
    from app.storage.model_store import ModelStore
    def create(index):
        ModelStore(tmp_path / "models.json").create(ModelConfigCreate(id=f"m{index}", name="local",
            model="fake", protocol="chat_completions", base_url="http://127.0.0.1", api_key="test"))
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(create, range(12)))
    assert len(ModelStore(tmp_path / "models.json").list()) == 12
    assert not list(tmp_path.glob("*.tmp"))


def test_startup_interrupts_tasks_and_advances_missed_schedules(tmp_path, monkeypatch):
    from datetime import timedelta
    from app.core.models import utc_now
    from app.intelligence.schemas import IntelligenceTask
    from app.storage.intelligence_task_store import IntelligenceTaskStore
    from app.suites.schemas import SuiteSchedule, SuiteRun, SuiteDefaultRunRequest
    from app.suites.store import SuiteScheduleStore, SuiteRunStore
    monkeypatch.setenv("LLM_BENCHMARK_DATA_DIR", str(tmp_path))
    request = SuiteDefaultRunRequest(model_id="local")
    suite = SuiteRunStore().save(SuiteRun(model_id="local", request=request, status="running"))
    task = IntelligenceTaskStore().save(IntelligenceTask(task_id="intel_task_stale", model_id="local", evalscope_base_url="in-process", status="running"))
    now = utc_now()
    store = SuiteScheduleStore()
    missed = store.save(SuiteSchedule(name="missed", model_id="local", request=request, next_run_at=now - timedelta(days=2)))
    once = store.save(SuiteSchedule(name="once", model_id="local", request=request, run_once=True, next_run_at=now - timedelta(days=1)))
    reconcile_startup()
    assert SuiteRunStore().get(suite.suite_id).status == "interrupted"
    assert IntelligenceTaskStore().get(task.task_id).status == "interrupted"
    assert store.get(missed.schedule_id).next_run_at > now
    assert store.get(once.schedule_id).enabled is False
    assert len(SuiteRunStore().list(limit=None)) == 1


def test_atomic_writer_waits_for_open_reader(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import app.storage.file_utils as files
    path = tmp_path / "record.json"
    files.write_json_file_atomic(path, {"value": 1})
    reading, release, writing, replacing = (threading.Event() for _ in range(4))
    original_load, original_replace = files.json.load, files.os.replace
    def blocked_load(handle):
        reading.set()
        assert release.wait(3)
        return original_load(handle)
    def replace(source, target):
        replacing.set()
        return original_replace(source, target)
    def write():
        writing.set()
        files.write_json_file_atomic(path, {"value": 2})
    monkeypatch.setattr(files.json, "load", blocked_load)
    monkeypatch.setattr(files.os, "replace", replace)
    with ThreadPoolExecutor(max_workers=2) as pool:
        reader = pool.submit(files.read_json_file, path, {})
        assert reading.wait(2)
        writer = pool.submit(write)
        try:
            assert writing.wait(2)
            assert not replacing.wait(.1)
        finally:
            release.set()
        assert reader.result(timeout=3) == {"value": 1}
        writer.result(timeout=3)
    assert files.read_json_file(path, {}) == {"value": 2}
