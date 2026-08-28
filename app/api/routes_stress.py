from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.api.errors import api_error
from app.evalscope_defaults import (
    DEFAULT_STRESS_DATASET,
    LOCAL_RESOLVABLE_STRESS_DATASETS,
    STRESS_DATASET_METADATA,
)
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


def _stress_dataset_metadata() -> dict:
    """Return stress dataset metadata, only showing locally available or built-in datasets.

    Non-local-resolvable datasets (random, speed_benchmark) are always shown
    because they don't require downloading. Local-resolvable datasets are only
    shown when the local file/directory exists in data/stress_datasets/.
    """
    datasets_dir = Path(os.getenv("LLM_BENCHMARK_STRESS_DATASETS_DIR", "data/stress_datasets"))
    result: dict[str, dict] = {}
    for name, meta in STRESS_DATASET_METADATA.items():
        row = dict(meta)
        row["name"] = name
        row["is_default"] = name == DEFAULT_STRESS_DATASET
        available_local = False
        local_path = None
        if name in LOCAL_RESOLVABLE_STRESS_DATASETS and datasets_dir.exists():
            candidate_dir = datasets_dir / name
            if candidate_dir.is_dir():
                available_local = True
                local_path = str(candidate_dir)
            else:
                for suffix in (".json", ".jsonl"):
                    candidate_file = datasets_dir / f"{name}{suffix}"
                    if candidate_file.is_file():
                        available_local = True
                        local_path = str(candidate_file)
                        break
        row["available_local"] = available_local
        if local_path:
            row["local_path"] = local_path
        # Skip local-resolvable datasets that aren't available locally;
        # showing them would trigger a ModelScope download on use.
        if name in LOCAL_RESOLVABLE_STRESS_DATASETS and not available_local:
            continue
        result[name] = row
    return {"total": len(result), "default_dataset": DEFAULT_STRESS_DATASET, "datasets": result}


@router.get("/datasets")
def stress_datasets():
    return _stress_dataset_metadata()


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


@router.post("/tasks/{task_id}/cancel")
async def cancel_stress_task(task_id: str):
    task = await _runner().cancel(task_id)
    if task is None:
        raise api_error(404, "stress_task_not_found", f"Stress task not found: {task_id}")
    return task


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

