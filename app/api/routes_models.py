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
        if str(exc).startswith("model_already_exists:"):
            raise api_error(400, "model_already_exists", f"Model config already exists: {config.id}")
        raise api_error(500, "storage_error", str(exc))


@router.get("", response_model=list[ModelConfigPublic])
def list_models():
    return [mask_model_config(item) for item in _store().list()]


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
    deleted = _store().delete(model_id)
    if not deleted:
        raise api_error(404, "model_not_found", f"Model config not found: {model_id}")
    return {"deleted": True}
