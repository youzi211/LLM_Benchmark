from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path

import pytest

from app.jobs.executor import JobExecutor
from app.jobs.store import JobStore
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
from app.suites.schemas import SuiteDefaultRunRequest, SuiteRun, SuiteScheduleCreate
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
        self.submitted_custom = None
        self.submitted_default = None
        self.cancelled_task_ids: list[str] = []

    async def submit_default(self, model_id: str, *, limit: int | None = None) -> IntelligenceTask:
        self.submitted_default = {"model_id": model_id, "limit": limit}
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

    async def submit_custom(self, *, model_id: str, datasets: list[str], limit: int | None = None, eval_batch_size: int | None = None, generation_config: dict | None = None, dataset_args: dict | None = None) -> IntelligenceTask:
        self.submitted_custom = {
            "model_id": model_id,
            "datasets": datasets,
            "limit": limit,
            "eval_batch_size": eval_batch_size,
            "generation_config": generation_config,
            "dataset_args": dataset_args,
        }
        task = await self.submit_default(model_id, limit=limit)
        task.datasets = datasets
        self.store.save(task)
        return task

    async def cancel(self, task_id: str) -> IntelligenceTask | None:
        self.cancelled_task_ids.append(task_id)
        task = self.store.get(task_id)
        if task is not None and task.status not in {"completed", "failed", "interrupted"}:
            task.status = "interrupted"
            task.progress = "任务已取消"
            task.completed_at = utc_now()
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
        self.cancelled_task_ids: list[str] = []

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

    async def cancel(self, task_id: str) -> StressTask | None:
        self.cancelled_task_ids.append(task_id)
        task = self.store.get(task_id)
        if task is not None and task.status not in {"completed", "failed", "interrupted"}:
            task.status = "interrupted"
            task.progress = "任务已取消"
            task.completed_at = utc_now()
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


@pytest.mark.asyncio
async def test_suite_runner_uses_custom_intelligence_profile_options(tmp_path: Path):
    data_dir = tmp_path / "data"
    reports_dir = tmp_path / "reports"
    intelligence_runner = FakeIntelligenceRunner(IntelligenceTaskStore(data_dir / "intelligence_tasks"))
    runner = SuiteRunner(
        suite_store=SuiteRunStore(data_dir / "suite_runs"),
        gateway_task_store=TaskStore(data_dir / "tasks"),
        intelligence_task_store=IntelligenceTaskStore(data_dir / "intelligence_tasks"),
        stress_task_store=StressTaskStore(data_dir / "stress_tasks"),
        gateway_runner=FakeGatewayRunner(TaskStore(data_dir / "tasks")),
        intelligence_runner=intelligence_runner,
        stress_runner=FakeStressRunner(StressTaskStore(data_dir / "stress_tasks")),
        reports_dir=reports_dir,
        poll_interval_seconds=0,
    )

    suite = await runner.start_default(
        SuiteDefaultRunRequest(
            model_id="demo-chat",
            run_gateway=False,
            run_stress=False,
            run_intelligence=True,
            intelligence_datasets=["gsm8k"],
            intelligence_limit=3,
            intelligence_eval_batch_size=2,
            intelligence_generation_config={"temperature": 0.0, "max_tokens": 64},
            wait_for_completion=True,
        )
    )

    assert suite.status == "completed"
    assert intelligence_runner.submitted_custom == {
        "model_id": "demo-chat",
        "datasets": ["gsm8k"],
        "limit": 3,
        "eval_batch_size": 2,
        "generation_config": {"temperature": 0.0, "max_tokens": 64},
        "dataset_args": None,
    }


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


class RecordingJobExecutor:
    def __init__(self):
        self.submissions: list[dict] = []

    def submit_async(self, *, job_type: str, target_id: str, payload: dict, func):
        self.submissions.append({"job_type": job_type, "target_id": target_id, "payload": payload, "func": func})
        return type("Job", (), {"job_id": f"job_{target_id}"})()


@pytest.mark.asyncio
async def test_suite_scheduler_triggers_due_schedule_and_updates_next_run(tmp_path: Path):
    schedule_store = SuiteScheduleStore(tmp_path / "suite_schedules")
    suite_runner = RecordingSuiteRunner()
    job_executor = RecordingJobExecutor()
    scheduler = SuiteScheduler(schedule_store=schedule_store, suite_runner_factory=lambda: suite_runner, job_executor=job_executor)
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
    # 调度器只提交 suite job，不直接 create_task 执行 suite。
    assert suite_runner.executed_suite_ids == []
    assert len(job_executor.submissions) == 1
    assert job_executor.submissions[0]["job_type"] == "suite"
    assert job_executor.submissions[0]["target_id"] == "suite_recorded"
    assert updated.last_job_id == "job_suite_recorded"


@pytest.mark.asyncio
async def test_suite_scheduler_disables_one_shot_schedule_after_trigger(tmp_path: Path):
    schedule_store = SuiteScheduleStore(tmp_path / "suite_schedules")
    suite_runner = RecordingSuiteRunner()
    job_executor = RecordingJobExecutor()
    scheduler = SuiteScheduler(schedule_store=schedule_store, suite_runner_factory=lambda: suite_runner, job_executor=job_executor)
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
    updated = schedule_store.get(schedule.schedule_id)
    assert triggered == 1
    assert len(suite_runner.requests) == 1
    assert updated is not None
    assert updated.run_once is True
    assert updated.enabled is False
    assert updated.run_count == 1
    assert suite_runner.executed_suite_ids == []
    assert len(job_executor.submissions) == 1
    assert updated.last_job_id == "job_suite_recorded"



class FailingExecuteSuiteRunner(RecordingSuiteRunner):
    async def execute(self, suite_id: str):
        self.executed_suite_ids.append(suite_id)
        raise RuntimeError("background explode")


@pytest.mark.asyncio
async def test_suite_scheduler_records_background_job_failure(tmp_path: Path, caplog):
    schedule_store = SuiteScheduleStore(tmp_path / "suite_schedules")
    suite_runner = FailingExecuteSuiteRunner()
    job_executor = JobExecutor(store=JobStore(tmp_path / "jobs"), max_concurrency=1)
    scheduler = SuiteScheduler(schedule_store=schedule_store, suite_runner_factory=lambda: suite_runner, job_executor=job_executor)
    due = SuiteScheduleCreate(
        name="nightly demo",
        model_id="demo-chat",
        time_of_day="02:00",
        next_run_at=utc_now() - timedelta(seconds=1),
        stress_parallel=[1],
        stress_number=[1],
    )
    schedule = schedule_store.create(due)

    with caplog.at_level("ERROR", logger="app.jobs.executor"):
        triggered = await scheduler.tick_once(now=utc_now())
        updated = schedule_store.get(schedule.schedule_id)
        assert updated is not None and updated.last_job_id is not None
        job = await job_executor.wait(updated.last_job_id, timeout=5)

    assert triggered == 1
    assert updated.last_error is None
    assert job is not None
    assert job.status == "failed"
    assert job.error == {"message": "background explode", "type": "RuntimeError"}
    assert suite_runner.executed_suite_ids == ["suite_recorded"]
    assert "Job failed" in caplog.text


@pytest.mark.asyncio
async def test_suite_runner_uses_custom_intelligence_profile_options(tmp_path: Path):
    data_dir = tmp_path / "data"
    reports_dir = tmp_path / "reports"
    intelligence_store = IntelligenceTaskStore(data_dir / "intelligence_tasks")
    intelligence_runner = FakeIntelligenceRunner(intelligence_store)
    runner = SuiteRunner(
        suite_store=SuiteRunStore(data_dir / "suite_runs"),
        gateway_task_store=TaskStore(data_dir / "tasks"),
        intelligence_task_store=intelligence_store,
        stress_task_store=StressTaskStore(data_dir / "stress_tasks"),
        gateway_runner=FakeGatewayRunner(TaskStore(data_dir / "tasks")),
        intelligence_runner=intelligence_runner,
        stress_runner=FakeStressRunner(StressTaskStore(data_dir / "stress_tasks")),
        reports_dir=reports_dir,
        poll_interval_seconds=0,
    )

    suite = await runner.start_default(
        SuiteDefaultRunRequest(
            model_id="demo-chat",
            run_gateway=False,
            run_stress=False,
            run_intelligence=True,
            intelligence_datasets=["gsm8k"],
            intelligence_limit=3,
            intelligence_eval_batch_size=2,
            intelligence_generation_config={"temperature": 0.0, "max_tokens": 64},
            wait_for_completion=True,
        )
    )

    assert suite.status == "completed"
    assert intelligence_runner.submitted_custom == {
        "model_id": "demo-chat",
        "datasets": ["gsm8k"],
        "limit": 3,
        "eval_batch_size": 2,
        "generation_config": {"temperature": 0.0, "max_tokens": 64},
        "dataset_args": None,
    }


@pytest.mark.asyncio
async def test_suite_runner_cancel_marks_current_step_and_cascades_child_tasks(tmp_path: Path):
    data_dir = tmp_path / "data"
    reports_dir = tmp_path / "reports"
    suite_store = SuiteRunStore(data_dir / "suite_runs")
    stress_store = StressTaskStore(data_dir / "stress_tasks")
    intelligence_store = IntelligenceTaskStore(data_dir / "intelligence_tasks")
    stress_runner = FakeStressRunner(stress_store)
    intelligence_runner = FakeIntelligenceRunner(intelligence_store)
    runner = SuiteRunner(
        suite_store=suite_store,
        gateway_task_store=TaskStore(data_dir / "tasks"),
        intelligence_task_store=intelligence_store,
        stress_task_store=stress_store,
        gateway_runner=FakeGatewayRunner(TaskStore(data_dir / "tasks")),
        intelligence_runner=intelligence_runner,
        stress_runner=stress_runner,
        reports_dir=reports_dir,
        poll_interval_seconds=0,
    )
    suite = await runner.start_default(
        SuiteDefaultRunRequest(model_id="demo-chat", run_gateway=False, run_stress=True, run_intelligence=True)
    )
    suite.status = "running"
    suite.current_step = "stress"
    suite.stress_task_id = "stress_task_suite"
    suite.intelligence_task_id = "intel_task_suite"
    suite.steps[1].status = "running"
    suite.steps[1].task_id = "stress_task_suite"
    suite_store.save(suite)
    stress_store.save(StressTask(task_id="stress_task_suite", model_id="demo-chat", protocol="chat_completions", evalscope_base_url="in-process", status="running"))
    intelligence_store.save(IntelligenceTask(task_id="intel_task_suite", model_id="demo-chat", evalscope_base_url="in-process", status="running"))

    cancelled = await runner.cancel(suite.suite_id)

    assert cancelled.status == "interrupted"
    assert cancelled.current_step is None
    assert cancelled.completed_at is not None
    assert stress_runner.cancelled_task_ids == ["stress_task_suite"]
    assert intelligence_runner.cancelled_task_ids == ["intel_task_suite"]
    steps = {step.name: step for step in cancelled.steps}
    assert steps["stress"].status == "interrupted"
    assert steps["intelligence"].status == "interrupted"
    assert steps["overview"].status == "skipped"


@pytest.mark.asyncio
async def test_suite_runner_cancel_completed_is_noop(tmp_path: Path):
    data_dir = tmp_path / "data"
    runner = SuiteRunner(
        suite_store=SuiteRunStore(data_dir / "suite_runs"),
        gateway_task_store=TaskStore(data_dir / "tasks"),
        intelligence_task_store=IntelligenceTaskStore(data_dir / "intelligence_tasks"),
        stress_task_store=StressTaskStore(data_dir / "stress_tasks"),
        gateway_runner=FakeGatewayRunner(TaskStore(data_dir / "tasks")),
        intelligence_runner=FakeIntelligenceRunner(IntelligenceTaskStore(data_dir / "intelligence_tasks")),
        stress_runner=FakeStressRunner(StressTaskStore(data_dir / "stress_tasks")),
        reports_dir=tmp_path / "reports",
    )
    suite = SuiteRun(
        suite_id="suite_completed",
        model_id="demo-chat",
        status="completed",
        request=SuiteDefaultRunRequest(model_id="demo-chat", run_gateway=False, run_stress=False, run_intelligence=True),
        completed_at=utc_now(),
    )
    runner.suite_store.save(suite)

    cancelled = await runner.cancel(suite.suite_id)

    assert cancelled.status == "completed"
