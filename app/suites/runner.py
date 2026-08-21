from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

from app.core.models import utc_now
from app.core.runner import TaskRunner
from app.intelligence.runner import IntelligenceRunner
from app.overview.report import build_overview_report, write_overview_markdown
from app.overview.schemas import OverviewReportRequest
from app.storage.intelligence_task_store import IntelligenceTaskStore
from app.storage.overview_report_store import OverviewReportStore
from app.storage.stress_task_store import StressTaskStore
from app.storage.task_store import TaskStore
from app.stress.runner import StressRunner
from app.stress.schemas import StressDefaultRunRequest
from app.suites.schemas import SuiteDefaultRunRequest, SuiteRun, SuiteStep
from app.suites.store import SuiteRunStore

TERMINAL_EVALSCOPE_STATUSES = {"completed", "failed"}


class SuiteRunner:
    def __init__(
        self,
        *,
        suite_store: SuiteRunStore | None = None,
        gateway_task_store: TaskStore | None = None,
        intelligence_task_store: IntelligenceTaskStore | None = None,
        stress_task_store: StressTaskStore | None = None,
        overview_report_store: OverviewReportStore | None = None,
        gateway_runner: Any | None = None,
        intelligence_runner: Any | None = None,
        stress_runner: Any | None = None,
        reports_dir: Path | None = None,
        poll_interval_seconds: float = 5,
    ):
        self.suite_store = suite_store or SuiteRunStore()
        self.gateway_task_store = gateway_task_store or TaskStore()
        self.intelligence_task_store = intelligence_task_store or IntelligenceTaskStore()
        self.stress_task_store = stress_task_store or StressTaskStore()
        self.overview_report_store = overview_report_store or OverviewReportStore()
        self.gateway_runner = gateway_runner or TaskRunner(task_store=self.gateway_task_store, reports_dir=reports_dir)
        self.intelligence_runner = intelligence_runner or IntelligenceRunner(task_store=self.intelligence_task_store, reports_dir=reports_dir)
        self.stress_runner = stress_runner or StressRunner(task_store=self.stress_task_store, reports_dir=reports_dir)
        self.reports_dir = reports_dir
        self.poll_interval_seconds = poll_interval_seconds

    async def start_default(self, request: SuiteDefaultRunRequest, *, schedule_id: str | None = None) -> SuiteRun:
        suite = SuiteRun(
            model_id=request.model_id,
            title=request.title,
            request=request,
            schedule_id=schedule_id,
            steps=self._initial_steps(request),
        )
        self.suite_store.save(suite)
        if request.wait_for_completion:
            return await self.execute(suite.suite_id)
        return suite

    async def execute(self, suite_id: str) -> SuiteRun:
        suite = self.suite_store.get(suite_id)
        if suite is None:
            raise ValueError(f"suite_not_found:{suite_id}")
        suite.status = "running"
        suite.started_at = suite.started_at or utc_now()
        suite.updated_at = utc_now()
        self.suite_store.save(suite)

        try:
            if suite.request.run_gateway:
                await self._run_gateway(suite)
            if suite.request.run_stress:
                await self._run_stress(suite)
            if suite.request.run_intelligence:
                await self._run_intelligence(suite)
            self._write_overview(suite)
            suite.status = "partial" if suite.errors else "completed"
        except Exception as exc:
            self._append_error(suite, "suite", exc)
            if any([suite.gateway_task_id, suite.intelligence_task_id, suite.stress_task_id]):
                try:
                    self._write_overview(suite)
                    suite.status = "partial"
                except Exception as overview_exc:
                    self._append_error(suite, "overview", overview_exc)
                    suite.status = "failed"
            else:
                suite.status = "failed"
        finally:
            suite.current_step = None
            suite.completed_at = utc_now()
            suite.updated_at = utc_now()
            self.suite_store.save(suite)
        return suite

    def _initial_steps(self, request: SuiteDefaultRunRequest) -> list[SuiteStep]:
        return [
            SuiteStep(name="gateway", title="网关接入验收", enabled=request.run_gateway, status="pending" if request.run_gateway else "skipped"),
            SuiteStep(name="stress", title="EvalScope 压测", enabled=request.run_stress, status="pending" if request.run_stress else "skipped"),
            SuiteStep(name="intelligence", title="EvalScope 能力评测", enabled=request.run_intelligence, status="pending" if request.run_intelligence else "skipped"),
            SuiteStep(name="overview", title="统一总览报告", enabled=True, status="pending"),
        ]

    def _step(self, suite: SuiteRun, name: str) -> SuiteStep:
        for step in suite.steps:
            if step.name == name:
                return step
        step = SuiteStep(name=name, title=name)
        suite.steps.append(step)
        return step

    def _start_step(self, suite: SuiteRun, name: str) -> SuiteStep:
        step = self._step(suite, name)
        step.status = "running"
        step.started_at = utc_now()
        suite.current_step = name
        suite.updated_at = utc_now()
        self.suite_store.save(suite)
        return step

    def _finish_step(self, suite: SuiteRun, name: str, *, task_id: str | None = None, failed: bool = False, message: str | None = None) -> None:
        step = self._step(suite, name)
        step.status = "failed" if failed else "completed"
        step.task_id = task_id or step.task_id
        step.message = message
        step.completed_at = utc_now()
        suite.updated_at = utc_now()
        self.suite_store.save(suite)

    async def _run_gateway(self, suite: SuiteRun) -> None:
        self._start_step(suite, "gateway")
        try:
            task = await self.gateway_runner.run(
                model_id=suite.model_id,
                plan_id=suite.request.gateway_plan_id,
                metric_ids=suite.request.gateway_metric_ids,
            )
            suite.gateway_task_id = task.task_id
            failed = task.status != "completed"
            if failed:
                suite.errors.append({"step": "gateway", "message": task.error or "gateway task failed"})
            self._finish_step(suite, "gateway", task_id=task.task_id, failed=failed)
        except Exception as exc:
            self._append_error(suite, "gateway", exc)
            self._finish_step(suite, "gateway", failed=True, message=str(exc))

    async def _run_intelligence(self, suite: SuiteRun) -> None:
        self._start_step(suite, "intelligence")
        try:
            task = await self.intelligence_runner.submit_default(suite.model_id, limit=suite.request.intelligence_limit)
            suite.intelligence_task_id = task.task_id
            self.suite_store.save(suite)
            task = await self._wait_for_intelligence(task.task_id, suite.request)
            failed = task is None or task.status != "completed"
            if failed:
                suite.errors.append({"step": "intelligence", "message": getattr(task, "error", None) or "intelligence task failed"})
            self._finish_step(suite, "intelligence", task_id=suite.intelligence_task_id, failed=failed)
        except Exception as exc:
            self._append_error(suite, "intelligence", exc)
            self._finish_step(suite, "intelligence", failed=True, message=str(exc))

    async def _run_stress(self, suite: SuiteRun) -> None:
        self._start_step(suite, "stress")
        try:
            stress_request = StressDefaultRunRequest.model_validate(suite.request.stress_options.to_stress_request_data(suite.model_id))
            task = await self.stress_runner.submit_default(suite.model_id, stress_request)
            suite.stress_task_id = task.task_id
            self.suite_store.save(suite)
            task = await self._wait_for_stress(task.task_id, suite.request)
            failed = task is None or task.status != "completed"
            if failed:
                suite.errors.append({"step": "stress", "message": getattr(task, "error", None) or "stress task failed"})
            self._finish_step(suite, "stress", task_id=suite.stress_task_id, failed=failed)
        except Exception as exc:
            self._append_error(suite, "stress", exc)
            self._finish_step(suite, "stress", failed=True, message=str(exc))

    async def _wait_for_intelligence(self, task_id: str, request: SuiteDefaultRunRequest):
        deadline = self._deadline(request)
        while True:
            task = await self.intelligence_runner.fetch_result(task_id)
            if task is None or task.status in TERMINAL_EVALSCOPE_STATUSES:
                return task
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError(f"intelligence task timeout: {task_id}")
            await asyncio.sleep(self._poll_interval(request))

    async def _wait_for_stress(self, task_id: str, request: SuiteDefaultRunRequest):
        deadline = self._deadline(request)
        while True:
            task = await self.stress_runner.fetch_result(task_id)
            if task is None or task.status in TERMINAL_EVALSCOPE_STATUSES:
                return task
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError(f"stress task timeout: {task_id}")
            await asyncio.sleep(self._poll_interval(request))

    def _write_overview(self, suite: SuiteRun) -> None:
        self._start_step(suite, "overview")
        report = build_overview_report(
            OverviewReportRequest(
                model_id=suite.model_id,
                gateway_task_id=suite.gateway_task_id,
                intelligence_task_id=suite.intelligence_task_id,
                stress_task_id=suite.stress_task_id,
                title=suite.request.title or "模型一键评测总览报告",
            ),
            task_store=self.gateway_task_store,
            intelligence_store=self.intelligence_task_store,
            stress_store=self.stress_task_store,
        )
        write_overview_markdown(report, reports_dir=self.reports_dir)
        self.overview_report_store.save(report)
        suite.overview_id = report.overview_id
        suite.overview_report_path = report.report_path
        self._finish_step(suite, "overview", task_id=report.overview_id)

    def _poll_interval(self, request: SuiteDefaultRunRequest) -> float:
        if request.poll_interval_seconds is not None:
            return request.poll_interval_seconds
        return self.poll_interval_seconds

    def _deadline(self, request: SuiteDefaultRunRequest) -> float | None:
        if request.timeout_seconds is None:
            return None
        return time.monotonic() + request.timeout_seconds

    def _append_error(self, suite: SuiteRun, step: str, exc: Exception) -> None:
        suite.errors.append({"step": step, "message": str(exc), "type": exc.__class__.__name__})
        suite.updated_at = utc_now()
        self.suite_store.save(suite)
