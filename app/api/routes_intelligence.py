from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.api.errors import api_error
from app.intelligence.config_store import EvalScopeConfigStore
from app.intelligence.evalscope_client import EvalScopeClient, EvalScopeClientError
from app.intelligence.runner import IntelligenceRunner
from app.intelligence.schemas import IntelligenceDefaultRunRequest, IntelligenceRunRequest
from app.storage.intelligence_task_store import IntelligenceTaskStore

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


def _client() -> EvalScopeClient:
    return EvalScopeClient(EvalScopeConfigStore().load())


def _runner() -> IntelligenceRunner:
    return IntelligenceRunner()


def _map_evalscope_error(exc: EvalScopeClientError):
    raise api_error(502, "evalscope_error", str(exc), {"status_code": exc.status_code})


@router.get("/evalscope/health")
async def evalscope_health():
    try:
        return await _client().health()
    except EvalScopeClientError as exc:
        _map_evalscope_error(exc)


@router.get("/evalscope/judge-config")
async def evalscope_judge_config():
    try:
        return await _client().judge_config()
    except EvalScopeClientError as exc:
        _map_evalscope_error(exc)


@router.get("/evalscope/tasks")
async def evalscope_tasks():
    try:
        return await _client().tasks()
    except EvalScopeClientError as exc:
        _map_evalscope_error(exc)


@router.get("/datasets")
async def datasets():
    try:
        return await _client().datasets()
    except EvalScopeClientError as exc:
        _map_evalscope_error(exc)


@router.get("/datasets/local")
async def local_datasets():
    try:
        return await _client().local_datasets()
    except EvalScopeClientError as exc:
        _map_evalscope_error(exc)


@router.post("/tasks/default")
async def submit_default_task(request: IntelligenceDefaultRunRequest):
    try:
        task = await _runner().submit_default(request.model_id)
    except ValueError as exc:
        text = str(exc)
        if text.startswith("model_not_found:"):
            raise api_error(404, "model_not_found", f"Model config not found: {request.model_id}")
        if text.startswith("model_disabled:"):
            raise api_error(400, "model_disabled", f"Model config is disabled: {request.model_id}")
        raise api_error(400, "invalid_intelligence_task_request", text)
    if task.status == "failed" and not task.evalscope_task_id:
        raise api_error(502, "evalscope_error", task.error.get("message", "EvalScope submit failed") if task.error else "EvalScope submit failed")
    return task


@router.post("/tasks")
async def submit_custom_task(request: IntelligenceRunRequest):
    try:
        task = await _runner().submit_custom(
            model_id=request.model_id,
            datasets=request.datasets,
            limit=request.limit,
            eval_batch_size=request.eval_batch_size,
            generation_config=request.generation_config,
        )
    except ValueError as exc:
        text = str(exc)
        if text.startswith("model_not_found:"):
            raise api_error(404, "model_not_found", f"Model config not found: {request.model_id}")
        if text.startswith("model_disabled:"):
            raise api_error(400, "model_disabled", f"Model config is disabled: {request.model_id}")
        raise api_error(400, "invalid_intelligence_task_request", text)
    if task.status == "failed" and not task.evalscope_task_id:
        raise api_error(502, "evalscope_error", task.error.get("message", "EvalScope submit failed") if task.error else "EvalScope submit failed")
    return task


@router.get("/tasks")
def list_intelligence_tasks(limit: int = 50):
    return IntelligenceTaskStore().list(limit=limit)


@router.get("/tasks/{task_id}")
async def get_intelligence_task(task_id: str):
    task = await _runner().refresh_status(task_id)
    if task is None:
        raise api_error(404, "intelligence_task_not_found", f"Intelligence task not found: {task_id}")
    return task


@router.get("/tasks/{task_id}/result")
async def get_intelligence_result(task_id: str):
    task = await _runner().fetch_result(task_id)
    if task is None:
        raise api_error(404, "intelligence_task_not_found", f"Intelligence task not found: {task_id}")
    return task


@router.get("/reports/{task_id}")
def get_intelligence_report(task_id: str):
    task = IntelligenceTaskStore().get(task_id)
    if task is None or not task.report_path:
        raise api_error(404, "intelligence_report_not_found", f"Intelligence report not found for task: {task_id}")
    path = Path(task.report_path)
    if not path.exists():
        raise api_error(404, "intelligence_report_not_found", f"Intelligence report not found for task: {task_id}")
    return FileResponse(path, media_type="text/markdown; charset=utf-8", filename=path.name)
