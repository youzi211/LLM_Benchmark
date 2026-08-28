from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.api.errors import api_error
from app.intelligence.config_store import EvalScopeConfigStore
from app.intelligence.evalscope_direct import evalscope_health, local_dataset_metadata, sandbox_health
from app.intelligence.runner import IntelligenceRunner
from app.intelligence.schemas import EvalScopeConfig, IntelligenceDefaultRunRequest, IntelligenceRunRequest
from app.storage.intelligence_task_store import IntelligenceTaskStore

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


SENSITIVE_CONFIG_KEYS = {"api_key", "apikey", "authorization", "password", "secret", "access_token", "bearer_token", "token"}


def _mask_config_value(key: str, value):
    if isinstance(value, dict):
        return {str(k): _mask_config_value(str(k), v) for k, v in value.items()}
    if isinstance(value, list):
        return [_mask_config_value(key, item) for item in value]
    if key.lower() in SENSITIVE_CONFIG_KEYS and value not in (None, ""):
        return "***"
    return value


def _public_evalscope_config(config: EvalScopeConfig) -> dict:
    data = config.model_dump(mode="json")
    data["sandbox_manager_config"] = _mask_config_value("sandbox_manager_config", data.get("sandbox_manager_config") or {})
    return data


def _config():
    return EvalScopeConfigStore().load()


def _merge_evalscope_config_update(current: EvalScopeConfig, update: EvalScopeConfig) -> EvalScopeConfig:
    data = current.model_dump(mode="json")
    update_data = update.model_dump(mode="json")
    for field in update.model_fields_set:
        if field == "sandbox_manager_config" and isinstance(update_data.get(field), dict):
            incoming = dict(update_data[field])
            if incoming:
                merged = dict(data.get(field) or {})
                merged.update(incoming)
                data[field] = merged
            else:
                data[field] = {}
        else:
            data[field] = update_data.get(field)
    return EvalScopeConfig.model_validate(data)


def _runner() -> IntelligenceRunner:
    return IntelligenceRunner()



def _ensure_local_datasets(datasets: list[str]) -> None:
    local = local_dataset_metadata(_config()).get("datasets", {})
    available = set(local.keys()) if isinstance(local, dict) else set()
    missing = [dataset for dataset in datasets if dataset not in available]
    if missing:
        raise ValueError(f"dataset_not_local:{', '.join(missing)}")


@router.get("/evalscope/health")
def evalscope_health_route():
    health = evalscope_health()
    if health.get("status") != "ok":
        raise api_error(502, "evalscope_error", health.get("error") or "EvalScope package is not available")
    return health


@router.get("/evalscope/judge-config")
def evalscope_judge_config():
    return _runner().judge_status()


@router.get("/evalscope/config")
def get_evalscope_config():
    return _public_evalscope_config(_config())


@router.put("/evalscope/config")
def update_evalscope_config(config: EvalScopeConfig):
    store = EvalScopeConfigStore()
    saved = store.save(_merge_evalscope_config_update(store.load(), config))
    return _public_evalscope_config(saved)


@router.get("/evalscope/sandbox-health")
def evalscope_sandbox_health(deep: bool = False):
    return sandbox_health(_config(), deep=deep)


@router.get("/evalscope/judge-health")
async def evalscope_judge_health():
    return await _runner().judge_health()


@router.get("/evalscope/tasks")
def evalscope_tasks(limit: int = 50):
    return {"mode": "in_process", "tasks": IntelligenceTaskStore().list(limit=limit)}


@router.get("/datasets")
def datasets():
    return local_dataset_metadata(_config())


@router.get("/datasets/local")
def local_datasets():
    return local_dataset_metadata(_config())


@router.post("/tasks/default")
async def submit_default_task(request: IntelligenceDefaultRunRequest):
    try:
        local_meta = local_dataset_metadata(_config())
        local_datasets = local_meta.get("datasets", {})
        default_datasets = local_meta.get("default_datasets") or (list(local_datasets.keys()) if isinstance(local_datasets, dict) else [])
        if not default_datasets:
            raise ValueError("dataset_not_local:default intelligence datasets")
        task = await _runner().submit_custom(model_id=request.model_id, datasets=default_datasets)
    except ValueError as exc:
        text = str(exc)
        if text.startswith("model_not_found:"):
            raise api_error(404, "model_not_found", f"Model config not found: {request.model_id}")
        if text.startswith("model_disabled:"):
            raise api_error(400, "model_disabled", f"Model config is disabled: {request.model_id}")
        if text.startswith("judge_required:"):
            raise api_error(400, "judge_required", text)
        if text.startswith("dataset_not_local:"):
            raise api_error(400, "dataset_not_local", text)
        raise api_error(400, "invalid_intelligence_task_request", text)
    return task


@router.post("/tasks")
async def submit_custom_task(request: IntelligenceRunRequest):
    try:
        _ensure_local_datasets(request.datasets)
        task = await _runner().submit_custom(
            model_id=request.model_id,
            datasets=request.datasets,
            limit=request.limit,
            eval_batch_size=request.eval_batch_size,
            generation_config=request.generation_config,
            dataset_args=request.dataset_args,
        )
    except ValueError as exc:
        text = str(exc)
        if text.startswith("model_not_found:"):
            raise api_error(404, "model_not_found", f"Model config not found: {request.model_id}")
        if text.startswith("model_disabled:"):
            raise api_error(400, "model_disabled", f"Model config is disabled: {request.model_id}")
        if text.startswith("judge_required:"):
            raise api_error(400, "judge_required", text)
        if text.startswith("dataset_not_local:"):
            raise api_error(400, "dataset_not_local", text)
        raise api_error(400, "invalid_intelligence_task_request", text)
    return task


@router.get("/tasks")
def list_intelligence_tasks(limit: int = 50):
    return IntelligenceTaskStore().list(limit=limit)


@router.post("/tasks/{task_id}/cancel")
async def cancel_intelligence_task(task_id: str):
    task = await _runner().cancel(task_id)
    if task is None:
        raise api_error(404, "intelligence_task_not_found", f"Intelligence task not found: {task_id}")
    return task


@router.get("/tasks/{task_id}/progress")
async def get_intelligence_task_progress(task_id: str):
    task = await _runner().refresh_status(task_id)
    if task is None:
        raise api_error(404, "intelligence_task_not_found", f"Intelligence task not found: {task_id}")
    return {
        "task_id": task.task_id,
        "status": task.status,
        "progress": task.progress,
        "progress_detail": task.progress_detail,
        "updated_at": task.updated_at,
    }


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

