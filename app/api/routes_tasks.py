from __future__ import annotations

import asyncio

from fastapi import APIRouter

from app.api.errors import api_error
from app.core.models import RunTaskRequest, TaskResult, utc_now
from app.core.registry import resolve_metric_ids
from app.core.runner import TaskRunner
from app.jobs.executor import get_job_executor
from app.jobs.schemas import new_job_id
from app.reports.markdown import redact_text
from app.storage.task_store import TaskStore
from app.utils.ids import new_task_id

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _raise_task_value_error(exc: ValueError) -> None:
    text = str(exc)
    if text.startswith("invalid_plan:"):
        raise api_error(400, "invalid_task_request", f"Invalid plan: {text.split(':', 1)[1]}")
    if text.startswith("invalid_metric:"):
        raise api_error(400, "invalid_metric", f"Invalid metric: {text.split(':', 1)[1]}")
    raise api_error(400, "invalid_task_request", text)


@router.post("/run")
async def run_task(request: RunTaskRequest):
    try:
        return await TaskRunner().run(model_id=request.model_id, plan_id=request.plan_id, metric_ids=request.metric_ids)
    except ValueError as exc:
        _raise_task_value_error(exc)


def _finish_interrupted(task_id: str) -> None:
    store = TaskStore()
    task = store.get(task_id)
    if task is None or task.status not in {"queued", "running"}:
        return
    task.status = "interrupted"
    task.finished_at = utc_now()
    task.duration_ms = (task.finished_at - task.started_at).total_seconds() * 1000
    task.error = {"code": "task_cancelled", "message": "Task cancelled by user"}
    store.save(task)


def _finish_failed(task_id: str, exc: Exception) -> None:
    store = TaskStore()
    task = store.get(task_id)
    if task is None or task.status not in {"queued", "running"}:
        return
    task.status = "error"
    task.finished_at = utc_now()
    task.duration_ms = (task.finished_at - task.started_at).total_seconds() * 1000
    task.error = {
        "code": "task_failed",
        "message": redact_text(str(exc)),
        "type": exc.__class__.__name__,
    }
    store.save(task)


async def _execute_basic_task(task_id: str, request: RunTaskRequest) -> None:
    try:
        await TaskRunner().run(
            model_id=request.model_id,
            plan_id=request.plan_id,
            metric_ids=request.metric_ids,
            task_id=task_id,
        )
    except asyncio.CancelledError:
        _finish_interrupted(task_id)
        raise
    except Exception as exc:
        _finish_failed(task_id, exc)
        raise


@router.post("/run-async", status_code=202)
async def run_task_async(request: RunTaskRequest):
    try:
        resolved = resolve_metric_ids(request.plan_id, request.metric_ids)
    except ValueError as exc:
        _raise_task_value_error(exc)

    task_id = new_task_id()
    job_id = new_job_id()
    store = TaskStore()
    task = TaskResult(
        task_id=task_id,
        job_id=job_id,
        status="queued",
        model_id=request.model_id,
        plan_id=request.plan_id,
        metric_ids=resolved,
        started_at=utc_now(),
    )
    store.save(task)
    try:
        job = get_job_executor().submit_async(
            job_type="basic",
            job_id=job_id,
            target_id=task_id,
            payload=request.model_dump(mode="json"),
            func=lambda: _execute_basic_task(task_id, request),
        )
    except Exception as exc:
        _finish_failed(task_id, exc)
        raise
    return {"task_id": task_id, "job_id": job.job_id, "status": task.status}


@router.get("")
def list_tasks(limit: int = 100):
    return [
        task.model_dump(mode="json", exclude={"analysis", "results"})
        for task in TaskStore().list(limit=limit)
    ]


@router.get("/{task_id}")
def get_task(task_id: str):
    task = TaskStore().get(task_id)
    if task is None:
        raise api_error(404, "task_not_found", f"Task not found: {task_id}")
    return task


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: str):
    store = TaskStore()
    task = store.get(task_id)
    if task is None:
        raise api_error(404, "task_not_found", f"Task not found: {task_id}")
    if task.status not in {"queued", "running"}:
        return task
    if not task.job_id:
        raise api_error(409, "task_not_cancellable", "Task does not have an active job")
    await get_job_executor().cancel(task.job_id)
    _finish_interrupted(task_id)
    return store.get(task_id) or task
