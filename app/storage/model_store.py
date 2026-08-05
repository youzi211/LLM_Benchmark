from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.core.models import ModelConfig, ModelConfigCreate, ModelConfigUpdate, utc_now
from app.storage.file_utils import read_json_file, write_json_file_atomic


class ModelStore:
    def __init__(self, path: Path | None = None):
        self.path = path or (Path(os.getenv("LLM_BENCHMARK_DATA_DIR", "data")) / "models.json")

    def _load_data(self) -> dict[str, Any]:
        data = read_json_file(self.path, {"models": []})
        if isinstance(data, list):
            return {"models": data, "analysis_model_id": None}
        if not isinstance(data, dict):
            return {"models": [], "analysis_model_id": None}
        return {
            "models": data.get("models", []),
            "analysis_model_id": data.get("analysis_model_id"),
        }

    def _load(self) -> list[ModelConfig]:
        data = self._load_data()
        return [ModelConfig.model_validate(item) for item in data.get("models", [])]

    def _write(self, models: list[ModelConfig], analysis_model_id: str | None) -> None:
        payload = {"models": [m.model_dump(mode="json") for m in models]}
        if analysis_model_id is not None:
            payload["analysis_model_id"] = analysis_model_id
        write_json_file_atomic(self.path, payload)

    def _save(self, models: list[ModelConfig]) -> None:
        self._write(models, self.get_analysis_model_id())

    def get_analysis_model_id(self) -> str | None:
        value = self._load_data().get("analysis_model_id")
        return value if isinstance(value, str) else None

    def set_analysis_model_id(self, model_id: str | None) -> None:
        self._write(self._load(), model_id)

    def list(self) -> list[ModelConfig]:
        return self._load()

    def get(self, model_id: str) -> ModelConfig | None:
        return next((m for m in self._load() if m.id == model_id), None)

    def create(self, config: ModelConfigCreate) -> ModelConfig:
        models = self._load()
        if any(m.id == config.id for m in models):
            raise ValueError(f"model_already_exists:{config.id}")
        created = ModelConfig(**config.model_dump())
        models.append(created)
        self._save(models)
        return created

    def update(self, model_id: str, patch: ModelConfigUpdate) -> ModelConfig:
        models = self._load()
        for index, model in enumerate(models):
            if model.id == model_id:
                data = model.model_dump()
                data.update(patch.model_dump(exclude_unset=True, exclude_none=True))
                data["updated_at"] = utc_now()
                updated = ModelConfig(**data)
                models[index] = updated
                self._save(models)
                return updated
        raise KeyError(f"model_not_found:{model_id}")

    def delete(self, model_id: str) -> bool:
        models = self._load()
        filtered = [m for m in models if m.id != model_id]
        if len(filtered) == len(models):
            return False
        self._save(filtered)
        return True
