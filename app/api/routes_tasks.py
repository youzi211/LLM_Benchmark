from __future__ import annotations

from fastapi import APIRouter

from app.api.errors import api_error
from app.core.models import RunTaskRequest
from app.core.runner import TaskRunner
from app.storage.task_store import TaskStore

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("/run")
async def run_task(request: RunTaskRequest):
    try:
        return await TaskRunner().run(model_id=request.model_id, plan_id=request.plan_id, metric_ids=request.metric_ids)
    except ValueError as exc:
        text = str(exc)
        if text.startswith("invalid_plan:"):
            raise api_error(400, "invalid_task_request", f"Invalid plan: {text.split(':', 1)[1]}")
        if text.startswith("invalid_metric:"):
            raise api_error(400, "invalid_metric", f"Invalid metric: {text.split(':', 1)[1]}")
        raise api_error(400, "invalid_task_request", text)


@router.get("")
def list_tasks(limit: int = 100):
    return TaskStore().list(limit=limit)


@router.get("/{task_id}")
def get_task(task_id: str):
    task = TaskStore().get(task_id)
    if task is None:
        raise api_error(404, "task_not_found", f"Task not found: {task_id}")
    return task
