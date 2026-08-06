from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.api.errors import api_error
from app.intelligence.config_store import EvalScopeConfigStore
from app.intelligence.evalscope_direct import evalscope_health
from app.storage.stress_task_store import StressTaskStore
from app.stress.runner import StressRunner
from app.stress.schemas import StressDefaultRunRequest, StressRunRequest

router = APIRouter(prefix="/stress", tags=["stress"])


def _runner() -> StressRunner:
    return StressRunner()


@router.get("/evalscope/health")
def evalscope_stress_health():
    health = evalscope_health()
    if health.get("status") != "ok":
        raise api_error(502, "evalscope_stress_error", health.get("error") or "EvalScope package is not available")
    return health


@router.post("/tasks/default")
async def submit_default_stress_task(request: StressDefaultRunRequest):
    try:
        task = await _runner().submit_default(request.model_id, request)
    except ValueError as exc:
        text = str(exc)
        if text.startswith("model_not_found:"):
            raise api_error(404, "model_not_found", f"Model config not found: {request.model_id}")
        if text.startswith("model_disabled:"):
            raise api_error(400, "model_disabled", f"Model config is disabled: {request.model_id}")
        raise api_error(400, "invalid_stress_task_request", text)
    return task


@router.post("/tasks")
async def submit_custom_stress_task(request: StressRunRequest):
    return await submit_default_stress_task(request)


@router.get("/tasks")
def list_stress_tasks(limit: int = 50):
    return StressTaskStore().list(limit=limit)


@router.get("/tasks/{task_id}")
async def get_stress_task(task_id: str):
    task = await _runner().refresh_status(task_id)
    if task is None:
        raise api_error(404, "stress_task_not_found", f"Stress task not found: {task_id}")
    return task


@router.get("/tasks/{task_id}/result")
async def get_stress_result(task_id: str):
    task = await _runner().fetch_result(task_id)
    if task is None:
        raise api_error(404, "stress_task_not_found", f"Stress task not found: {task_id}")
    return task


@router.get("/reports/{task_id}")
def get_stress_report(task_id: str):
    task = StressTaskStore().get(task_id)
    if task is None or not task.report_path:
        raise api_error(404, "stress_report_not_found", f"Stress report not found for task: {task_id}")
    path = Path(task.report_path)
    if not path.exists():
        raise api_error(404, "stress_report_not_found", f"Stress report not found for task: {task_id}")
    return FileResponse(path, media_type="text/markdown; charset=utf-8", filename=path.name)
