from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.api.errors import api_error
from app.storage.task_store import TaskStore

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/{task_id}")
def get_report(task_id: str):
    task = TaskStore().get(task_id)
    if task is None or not task.report_path:
        raise api_error(404, "report_not_found", f"Report not found for task: {task_id}")
    path = Path(task.report_path)
    if not path.exists():
        raise api_error(404, "report_not_found", f"Report not found for task: {task_id}")
    return FileResponse(path, media_type="text/markdown; charset=utf-8", filename=path.name)
