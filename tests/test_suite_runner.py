from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path

import pytest

from app.core.models import MetricResult, TaskResult, utc_now
from app.intelligence.schemas import (
    IntelligenceCategorySummary,
    IntelligenceDatasetResult,
    IntelligenceNormalizedResult,
    IntelligenceTask,
)
from app.storage.intelligence_task_store import IntelligenceTaskStore
from app.storage.stress_task_store import StressTaskStore
from app.storage.task_store import TaskStore
from app.stress.schemas import StressNormalizedResult, StressRunResult, StressTask
from app.suites.runner import SuiteRunner
from app.suites.scheduler import SuiteScheduler
from app.suites.schemas import SuiteDefaultRunRequest, SuiteScheduleCreate
from app.suites.store import SuiteScheduleStore, SuiteRunStore


class FakeGatewayRunner:
    def __init__(self, store: TaskStore):
        self.store = store

    async def run(self, model_id: str, plan_id: str, metric_ids: list[str] | None = None) -> TaskResult:
        task = TaskResult(
            task_id="task_gateway_suite",
            status="completed",
            model_id=model_id,
            model_config_name="Demo",
            upstream_model_name="demo-chat",
            protocol="chat_completions",
            plan_id=plan_id,
            metric_ids=metric_ids or ["connectivity"],
            started_at=utc_now(),
            finished_at=utc_now(),
            results=[MetricResult(metric_id="connectivity", metric_name="连通性", status="completed", summary="ok")],
            report_path="reports/2026-08-06/task_gateway_suite.md",
        )
        self.store.save(task)
        return task


class FakeIntelligenceRunner:
    def __init__(self, store: IntelligenceTaskStore):
        self.store = store

    async def submit_default(self, model_id: str, *, limit: int | None = None) -> IntelligenceTask:
        task = IntelligenceTask(
            task_id="intel_task_suite",
            evalscope_task_id="eval_intel_suite",
            model_id=model_id,
            model_config_name="Demo",
            upstream_model_name="demo-chat",
            evalscope_base_url="in-process",
            datasets=["gsm8k"],
            status="running",
        )
        self.store.save(task)
        return task

    async def fetch_result(self, task_id: str) -> IntelligenceTask | None:
        task = self.store.get(task_id)
        assert task is not None
        task.status = "completed"
        task.normalized_result = IntelligenceNormalizedResult(
            task_id=task.task_id,
            evalscope_task_id=task.evalscope_task_id,
            model="demo-chat",
            datasets=["gsm8k"],
            status="completed",
            dataset_results=[
                IntelligenceDatasetResult(dataset="gsm8k", pretty_name="GSM8K", categories=["数学"], score=80.0)
            ],
            category_summaries=[IntelligenceCategorySummary(category="数学", dataset_count=1, scored_dataset_count=1, average_score=80.0)],
        )
        task.report_path = "reports/intelligence/2026-08-06/intel_task_suite.md"
        task.completed_at = utc_now()
        self.store.save(task)
        return task


class FakeStressRunner:
    def __init__(self, store: StressTaskStore):
        self.store = store

    async def submit_default(self, model_id: str, options=None) -> StressTask:
        task = StressTask(
            task_id="stress_task_suite",
            evalscope_stress_task_id="eval_stress_suite",
            model_id=model_id,
            model_config_name="Demo",
            upstream_model_name="demo-chat",
            protocol="chat_completions",
            evalscope_base_url="in-process",
            status="running",
        )
        self.store.save(task)
        return task

    async def fetch_result(self, task_id: str) -> StressTask | None:
        task = self.store.get(task_id)
        assert task is not None
        task.status = "completed"
        task.normalized_result = StressNormalizedResult(
            task_id=task.task_id,
            evalscope_stress_task_id=task.evalscope_stress_task_id,
            model="demo-chat",
            status="completed",
            summary={"max_success_parallel": 5, "best_req_throughput": 12.5, "first_error_parallel": None},
            runs=[StressRunResult(parallel=5, number=50, total=50, success=50, failed=0, request_throughput=12.5)],
        )
        task.report_path = "reports/stress/2026-08-06/stress_task_suite.md"
        task.completed_at = utc_now()
        self.store.save(task)
        return task


@pytest.mark.asyncio
async def test_suite_runner_runs_all_components_and_creates_overview(tmp_path: Path):
    data_dir = tmp_path / "data"
    reports_dir = tmp_path / "reports"
    gateway_store = TaskStore(data_dir / "tasks")
    intelligence_store = IntelligenceTaskStore(data_dir / "intelligence_tasks")
    stress_store = StressTaskStore(data_dir / "stress_tasks")
    suite_store = SuiteRunStore(data_dir / "suite_runs")

    runner = SuiteRunner(
        suite_store=suite_store,
        gateway_task_store=gateway_store,
        intelligence_task_store=intelligence_store,
        stress_task_store=stress_store,
        gateway_runner=FakeGatewayRunner(gateway_store),
        intelligence_runner=FakeIntelligenceRunner(intelligence_store),
        stress_runner=FakeStressRunner(stress_store),
        reports_dir=reports_dir,
        poll_interval_seconds=0,
    )

    suite = await runner.start_default(SuiteDefaultRunRequest(model_id="demo-chat", wait_for_completion=True))

    assert suite.status == "completed"
    assert suite.gateway_task_id == "task_gateway_suite"
    assert suite.intelligence_task_id == "intel_task_suite"
    assert suite.stress_task_id == "stress_task_suite"
    assert suite.overview_id is not None
    assert suite.overview_report_path is not None
    assert Path(suite.overview_report_path).exists()
    assert "一眼看懂" in Path(suite.overview_report_path).read_text(encoding="utf-8")
    assert suite_store.get(suite.suite_id).overview_id == suite.overview_id


class RecordingSuiteRunner:
    def __init__(self):
        self.requests: list[SuiteDefaultRunRequest] = []
        self.executed_suite_ids: list[str] = []

    async def start_default(self, request: SuiteDefaultRunRequest, **kwargs):
        self.requests.append(request)
        return type("Suite", (), {"suite_id": "suite_recorded"})()

    async def execute(self, suite_id: str):
        # 记录后台执行被投递；真实 runner 这里会跑完整条 suite，但调度器不应阻塞等待它。
        self.executed_suite_ids.append(suite_id)
        return type("Suite", (), {"suite_id": suite_id, "status": "completed"})()


@pytest.mark.asyncio
async def test_suite_scheduler_triggers_due_schedule_and_updates_next_run(tmp_path: Path):
    schedule_store = SuiteScheduleStore(tmp_path / "suite_schedules")
    suite_runner = RecordingSuiteRunner()
    scheduler = SuiteScheduler(schedule_store=schedule_store, suite_runner_factory=lambda: suite_runner)
    due = SuiteScheduleCreate(
        name="nightly demo",
        model_id="demo-chat",
        time_of_day="02:00",
        next_run_at=utc_now() - timedelta(seconds=1),
        stress_parallel=[1],
        stress_number=[1],
    )
    schedule = schedule_store.create(due)

    triggered = await scheduler.tick_once(now=utc_now())
    # 让被投递的后台 execute 任务有机会运行（fire-and-forget via asyncio.create_task）。
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    updated = schedule_store.get(schedule.schedule_id)
    assert triggered == 1
    assert len(suite_runner.requests) == 1
    assert suite_runner.requests[0].model_id == "demo-chat"
    assert suite_runner.requests[0].stress_options.parallel == [1]
    assert updated is not None
    assert updated.last_suite_id == "suite_recorded"
    assert updated.last_run_at is not None
    assert updated.next_run_at > utc_now()
    assert updated.run_count == 1
    # 调度器投递了后台执行任务，且调度器自身没有阻塞等待其完成。
    assert suite_runner.executed_suite_ids == ["suite_recorded"]


@pytest.mark.asyncio
async def test_suite_scheduler_disables_one_shot_schedule_after_trigger(tmp_path: Path):
    schedule_store = SuiteScheduleStore(tmp_path / "suite_schedules")
    suite_runner = RecordingSuiteRunner()
    scheduler = SuiteScheduler(schedule_store=schedule_store, suite_runner_factory=lambda: suite_runner)
    due = SuiteScheduleCreate(
        name="one shot demo",
        model_id="demo-chat",
        time_of_day="00:00",
        run_once=True,
        next_run_at=utc_now() - timedelta(seconds=1),
        stress_parallel=[1],
        stress_number=[1],
    )
    schedule = schedule_store.create(due)

    triggered = await scheduler.tick_once(now=utc_now())
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    updated = schedule_store.get(schedule.schedule_id)
    assert triggered == 1
    assert len(suite_runner.requests) == 1
    assert updated is not None
    assert updated.run_once is True
    assert updated.enabled is False
    assert updated.run_count == 1
    assert suite_runner.executed_suite_ids == ["suite_recorded"]


class FailingExecuteSuiteRunner(RecordingSuiteRunner):
    async def execute(self, suite_id: str):
        self.executed_suite_ids.append(suite_id)
        raise RuntimeError("background explode")


@pytest.mark.asyncio
async def test_suite_scheduler_logs_background_execute_failure(tmp_path: Path, caplog):
    schedule_store = SuiteScheduleStore(tmp_path / "suite_schedules")
    suite_runner = FailingExecuteSuiteRunner()
    scheduler = SuiteScheduler(schedule_store=schedule_store, suite_runner_factory=lambda: suite_runner)
    due = SuiteScheduleCreate(
        name="nightly demo",
        model_id="demo-chat",
        time_of_day="02:00",
        next_run_at=utc_now() - timedelta(seconds=1),
        stress_parallel=[1],
        stress_number=[1],
    )
    schedule = schedule_store.create(due)

    with caplog.at_level("ERROR", logger="app.suites.scheduler"):
        triggered = await scheduler.tick_once(now=utc_now())
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    updated = schedule_store.get(schedule.schedule_id)
    assert triggered == 1
    assert updated is not None
    assert updated.last_error is None
    assert "Scheduled suite background execution failed" in caplog.text
    assert schedule.schedule_id in caplog.text
    assert "suite_recorded" in caplog.text
    assert "background explode" in caplog.text
