from __future__ import annotations

from fastapi import APIRouter

from app.api.errors import api_error
from app.core.models import ModelConfigCreate, ModelConfigPublic, ModelConfigUpdate
from app.storage.model_store import ModelStore
from app.utils.masking import mask_model_config

router = APIRouter(prefix="/models", tags=["models"])


def _store() -> ModelStore:
    return ModelStore()


@router.post("", response_model=ModelConfigPublic)
def create_model(config: ModelConfigCreate):
    try:
        return mask_model_config(_store().create(config))
    except ValueError as exc:
        if str(exc).startswith("model_id_reserved:"):
            raise api_error(409, "model_id_reserved", "模型 ID 存在历史记录，禁止复用")
        if str(exc).startswith("model_already_exists:"):
            raise api_error(400, "model_already_exists", f"Model config already exists: {config.id}")
        raise api_error(500, "storage_error", str(exc))


@router.get("", response_model=list[ModelConfigPublic])
def list_models(include_archived: bool = False):
    return [mask_model_config(item) for item in _store().list(include_archived=include_archived)]


@router.get("/{model_id}", response_model=ModelConfigPublic)
def get_model(model_id: str):
    model = _store().get(model_id)
    if model is None:
        raise api_error(404, "model_not_found", f"Model config not found: {model_id}")
    return mask_model_config(model)


@router.put("/{model_id}", response_model=ModelConfigPublic)
def update_model(model_id: str, patch: ModelConfigUpdate):
    try:
        return mask_model_config(_store().update(model_id, patch))
    except KeyError:
        raise api_error(404, "model_not_found", f"Model config not found: {model_id}")
    except Exception as exc:
        raise api_error(500, "storage_error", str(exc))


@router.delete("/{model_id}")
def delete_model(model_id: str):
    try:
        deleted = _store().delete(model_id)
    except ValueError:
        raise api_error(409, "model_has_history", "模型存在评测历史，请使用归档操作")
    if not deleted:
        raise api_error(404, "model_not_found", f"Model config not found: {model_id}")
    return {"deleted": True}


@router.post("/{model_id}/archive", response_model=ModelConfigPublic)
def archive_model(model_id: str):
    from app.intelligence.config_store import EvalScopeConfigStore
    from app.suites.store import SuiteScheduleStore
    import os
    store = _store()
    references = []
    if store.get_analysis_model_id() == model_id:
        references.append("analysis_model_id")
    if EvalScopeConfigStore().load().judge_model_config_id == model_id:
        references.append("judge_model_config_id")
    if os.getenv("LLM_BENCHMARK_EVALSCOPE_JUDGE_MODEL_CONFIG_ID") == model_id:
        references.append("environment_judge")
    references.extend(s.schedule_id for s in SuiteScheduleStore().list(limit=None) if s.enabled and s.model_id == model_id)
    if references:
        raise api_error(409, "model_in_use", "请先解除默认模型或定时任务引用", {"references": references})
    try:
        return mask_model_config(store.archive(model_id))
    except KeyError:
        raise api_error(404, "model_not_found", "模型不存在")


@router.post("/{model_id}/restore", response_model=ModelConfigPublic)
def restore_model(model_id: str):
    try:
        return mask_model_config(_store().archive(model_id, restore=True))
    except KeyError:
        raise api_error(404, "model_not_found", "模型不存在")
