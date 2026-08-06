from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.api.errors import api_error
from app.intelligence.config_store import EvalScopeConfigStore
from app.intelligence.evalscope_direct import dataset_metadata, evalscope_health, local_dataset_metadata
from app.intelligence.runner import IntelligenceRunner
from app.intelligence.schemas import IntelligenceDefaultRunRequest, IntelligenceRunRequest
from app.storage.intelligence_task_store import IntelligenceTaskStore

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


def _config():
    return EvalScopeConfigStore().load()


def _runner() -> IntelligenceRunner:
    return IntelligenceRunner()


@router.get("/evalscope/health")
def evalscope_health_route():
    health = evalscope_health()
    if health.get("status") != "ok":
        raise api_error(502, "evalscope_error", health.get("error") or "EvalScope package is not available")
    return health


@router.get("/evalscope/judge-config")
def evalscope_judge_config():
    return _runner().judge_status()


@router.get("/evalscope/tasks")
def evalscope_tasks(limit: int = 50):
    return {"mode": "in_process", "tasks": IntelligenceTaskStore().list(limit=limit)}


@router.get("/datasets")
def datasets():
    return dataset_metadata(_config())


@router.get("/datasets/local")
def local_datasets():
    return local_dataset_metadata(_config())


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
        if text.startswith("judge_required:"):
            raise api_error(400, "judge_required", text)
        raise api_error(400, "invalid_intelligence_task_request", text)
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
        if text.startswith("judge_required:"):
            raise api_error(400, "judge_required", text)
        raise api_error(400, "invalid_intelligence_task_request", text)
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
