from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.api.errors import api_error
from app.core.runner import TaskRunner
from app.intelligence.runner import IntelligenceRunner
from app.jobs.executor import get_job_executor
from app.stress.runner import StressRunner
from app.suites.runner import SuiteRunner
from app.suites.schemas import SuiteDefaultRunRequest, SuiteQuickRunRequest, SuiteScheduleCreate, SuiteScheduleLastRun
from app.suites.profiles import EvalScopeProfileStore
from app.suites.store import SuiteRunStore, SuiteScheduleStore
from app.suites.transient_model_store import TransientModelStore

router = APIRouter(prefix="/suites", tags=["suites"])


def _runner() -> SuiteRunner:
    return SuiteRunner()


def _job_executor():
    return get_job_executor()


def _quick_runner(request: SuiteQuickRunRequest) -> tuple[SuiteRunner, SuiteDefaultRunRequest]:
    model = request.to_inline_model_config()
    model_store = TransientModelStore([model])
    runner = SuiteRunner(
        gateway_runner=TaskRunner(model_store=model_store),
        intelligence_runner=IntelligenceRunner(model_store=model_store),
        stress_runner=StressRunner(model_store=model_store),
    )
    return runner, request.to_suite_request(model.id)


async def _run_suite_job(runner: SuiteRunner, suite_id: str):
    return await runner.execute(suite_id)


async def _submit_suite_job(runner: SuiteRunner, suite, *, wait_for_completion: bool):
    if suite.status in {"completed", "partial", "failed", "interrupted"}:
        return suite
    job = _job_executor().submit_async(
        job_type="suite",
        target_id=suite.suite_id,
        payload={"suite_id": suite.suite_id, "schedule_id": suite.schedule_id},
        func=lambda: _run_suite_job(runner, suite.suite_id),
    )
    suite.job_id = job.job_id
    if hasattr(runner, "suite_store"):
        runner.suite_store.save(suite)
    else:
        SuiteRunStore().save(suite)
    if wait_for_completion:
        await _job_executor().wait(job.job_id)
        return runner.suite_store.get(suite.suite_id) or suite
    return suite


@router.post("/default")
async def start_default_suite(request: SuiteDefaultRunRequest):
    runner = _runner()
    start_request = request.model_copy(update={"wait_for_completion": False})
    try:
        suite = await runner.start_default(start_request)
    except ValueError as exc:
        text = str(exc)
        if text.startswith("model_not_found:"):
            raise api_error(404, "model_not_found", f"Model config not found: {request.model_id}")
        if text.startswith("model_disabled:"):
            raise api_error(400, "model_disabled", f"Model config is disabled: {request.model_id}")
        raise api_error(400, "invalid_suite_request", text)
    return await _submit_suite_job(runner, suite, wait_for_completion=request.wait_for_completion)


@router.post("/quick")
async def start_quick_suite(request: SuiteQuickRunRequest):
    runner, suite_request = _quick_runner(request)
    start_request = suite_request.model_copy(update={"wait_for_completion": False})
    try:
        suite = await runner.start_default(start_request)
    except ValueError as exc:
        text = str(exc)
        if text.startswith("model_disabled:"):
            raise api_error(400, "model_disabled", f"Model config is disabled: {suite_request.model_id}")
        raise api_error(400, "invalid_suite_request", text)
    return await _submit_suite_job(runner, suite, wait_for_completion=request.wait_for_completion)


@router.get("")
def list_suites(limit: int = 50):
    return SuiteRunStore().list(limit=limit)


@router.get("/profiles")
def list_suite_profiles():
    store = EvalScopeProfileStore()
    return [p.model_dump() for p in store.list()]


@router.post("/schedules")
def create_suite_schedule(request: SuiteScheduleCreate):
    try:
        return SuiteScheduleStore().create(request)
    except ValueError as exc:
        text = str(exc)
        if text.startswith("profile_not_found:"):
            profile_id = text.split(":", 1)[1]
            raise api_error(400, "profile_not_found", f"EvalScope profile not found: {profile_id}")
        if text.startswith("profile_requires_sandbox:"):
            profile_id = text.split(":", 1)[1]
            raise api_error(400, "profile_requires_sandbox", f"EvalScope profile requires sandbox but sandbox is disabled: {profile_id}")
        raise api_error(400, "invalid_suite_schedule", text)


@router.get("/schedules")
def list_suite_schedules(limit: int = 50):
    return SuiteScheduleStore().list(limit=limit)


@router.get("/schedules/{schedule_id}/last-run", response_model=SuiteScheduleLastRun)
def get_suite_schedule_last_run(schedule_id: str):
    schedule = SuiteScheduleStore().get(schedule_id)
    if schedule is None:
        raise api_error(404, "suite_schedule_not_found", f"Suite schedule not found: {schedule_id}")
    suite = SuiteRunStore().get(schedule.last_suite_id) if schedule.last_suite_id else None
    errors = suite.errors if suite is not None else []
    return SuiteScheduleLastRun(
        schedule=schedule,
        suite=suite,
        last_suite_status=suite.status if suite is not None else None,
        last_suite_current_step=suite.current_step if suite is not None else None,
        last_suite_error_count=len(errors),
        last_suite_errors=errors,
    )


@router.get("/schedules/{schedule_id}")
def get_suite_schedule(schedule_id: str):
    schedule = SuiteScheduleStore().get(schedule_id)
    if schedule is None:
        raise api_error(404, "suite_schedule_not_found", f"Suite schedule not found: {schedule_id}")
    return schedule


@router.delete("/schedules/{schedule_id}")
def delete_suite_schedule(schedule_id: str):
    deleted = SuiteScheduleStore().delete(schedule_id)
    if not deleted:
        raise api_error(404, "suite_schedule_not_found", f"Suite schedule not found: {schedule_id}")
    return {"deleted": True, "schedule_id": schedule_id}


@router.post("/schedules/{schedule_id}/trigger")
async def trigger_suite_schedule(schedule_id: str, wait_for_completion: bool = False):
    schedule_store = SuiteScheduleStore()
    schedule = schedule_store.get(schedule_id)
    if schedule is None:
        raise api_error(404, "suite_schedule_not_found", f"Suite schedule not found: {schedule_id}")
    runner = _runner()
    request = schedule.request.model_copy(update={"wait_for_completion": False})
    suite = await runner.start_default(request, schedule_id=schedule.schedule_id)
    schedule.last_suite_id = suite.suite_id
    schedule.last_run_at = suite.created_at
    schedule.run_count += 1
    job = _job_executor().submit_async(
        job_type="suite",
        target_id=suite.suite_id,
        payload={"suite_id": suite.suite_id, "schedule_id": schedule.schedule_id},
        func=lambda: _run_suite_job(runner, suite.suite_id),
    )
    suite.job_id = job.job_id
    if hasattr(runner, "suite_store"):
        runner.suite_store.save(suite)
    else:
        SuiteRunStore().save(suite)
    schedule.last_job_id = job.job_id
    if schedule.run_once:
        schedule.enabled = False
    schedule_store.save(schedule)
    if wait_for_completion:
        await _job_executor().wait(job.job_id)
        return runner.suite_store.get(suite.suite_id) or suite
    return suite


@router.post("/{suite_id}/cancel")
async def cancel_suite(suite_id: str):
    suite = await _runner().cancel(suite_id)
    if suite is None:
        raise api_error(404, "suite_not_found", f"Suite not found: {suite_id}")
    return suite


@router.get("/{suite_id}")
def get_suite(suite_id: str):
    suite = SuiteRunStore().get(suite_id)
    if suite is None:
        raise api_error(404, "suite_not_found", f"Suite not found: {suite_id}")
    return suite


@router.get("/{suite_id}/report")
def get_suite_report(suite_id: str):
    suite = SuiteRunStore().get(suite_id)
    if suite is None or not suite.overview_report_path:
        raise api_error(404, "suite_report_not_found", f"Suite report not found: {suite_id}")
    path = Path(suite.overview_report_path)
    if not path.exists():
        raise api_error(404, "suite_report_not_found", f"Suite report not found: {suite_id}")
    return FileResponse(path, media_type="text/markdown; charset=utf-8", filename=path.name)
