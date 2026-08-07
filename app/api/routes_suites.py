from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import FileResponse

from app.api.errors import api_error
from app.core.runner import TaskRunner
from app.intelligence.runner import IntelligenceRunner
from app.stress.runner import StressRunner
from app.suites.runner import SuiteRunner
from app.suites.schemas import SuiteDefaultRunRequest, SuiteQuickRunRequest, SuiteScheduleCreate
from app.suites.store import SuiteRunStore, SuiteScheduleStore
from app.suites.transient_model_store import TransientModelStore

router = APIRouter(prefix="/suites", tags=["suites"])


def _runner() -> SuiteRunner:
    return SuiteRunner()


def _quick_runner(request: SuiteQuickRunRequest) -> tuple[SuiteRunner, SuiteDefaultRunRequest]:
    model = request.to_inline_model_config()
    model_store = TransientModelStore([model])
    runner = SuiteRunner(
        gateway_runner=TaskRunner(model_store=model_store),
        intelligence_runner=IntelligenceRunner(model_store=model_store),
        stress_runner=StressRunner(model_store=model_store),
    )
    return runner, request.to_suite_request(model.id)


async def _execute_suite_background(suite_id: str) -> None:
    await _runner().execute(suite_id)


@router.post("/default")
async def start_default_suite(request: SuiteDefaultRunRequest, background_tasks: BackgroundTasks):
    try:
        suite = await _runner().start_default(request)
    except ValueError as exc:
        text = str(exc)
        if text.startswith("model_not_found:"):
            raise api_error(404, "model_not_found", f"Model config not found: {request.model_id}")
        if text.startswith("model_disabled:"):
            raise api_error(400, "model_disabled", f"Model config is disabled: {request.model_id}")
        raise api_error(400, "invalid_suite_request", text)
    if request.wait_for_completion:
        return suite
    background_tasks.add_task(_execute_suite_background, suite.suite_id)
    return suite


@router.post("/quick")
async def start_quick_suite(request: SuiteQuickRunRequest, background_tasks: BackgroundTasks):
    runner, suite_request = _quick_runner(request)
    try:
        suite = await runner.start_default(suite_request)
    except ValueError as exc:
        text = str(exc)
        if text.startswith("model_disabled:"):
            raise api_error(400, "model_disabled", f"Model config is disabled: {suite_request.model_id}")
        raise api_error(400, "invalid_suite_request", text)
    if request.wait_for_completion:
        return suite
    background_tasks.add_task(runner.execute, suite.suite_id)
    return suite


@router.get("")
def list_suites(limit: int = 50):
    return SuiteRunStore().list(limit=limit)


@router.post("/schedules")
def create_suite_schedule(request: SuiteScheduleCreate):
    return SuiteScheduleStore().create(request)


@router.get("/schedules")
def list_suite_schedules(limit: int = 50):
    return SuiteScheduleStore().list(limit=limit)


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
async def trigger_suite_schedule(schedule_id: str, background_tasks: BackgroundTasks, wait_for_completion: bool = False):
    schedule_store = SuiteScheduleStore()
    schedule = schedule_store.get(schedule_id)
    if schedule is None:
        raise api_error(404, "suite_schedule_not_found", f"Suite schedule not found: {schedule_id}")
    request = schedule.request.model_copy(update={"wait_for_completion": wait_for_completion})
    suite = await _runner().start_default(request, schedule_id=schedule.schedule_id)
    schedule.last_suite_id = suite.suite_id
    schedule.last_run_at = suite.created_at
    schedule.run_count += 1
    if schedule.run_once:
        schedule.enabled = False
    schedule_store.save(schedule)
    if not wait_for_completion:
        background_tasks.add_task(_execute_suite_background, suite.suite_id)
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
