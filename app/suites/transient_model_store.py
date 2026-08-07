from __future__ import annotations

from app.core.models import ModelConfig


class TransientModelStore:
    """In-memory model store for per-request evaluations.

    It intentionally implements only the read methods used by runners and report
    analysis, so inline API keys are never written to data/models.json.
    """

    def __init__(self, models: list[ModelConfig], *, analysis_model_id: str | None = None):
        self._models = {model.id: model for model in models}
        self._analysis_model_id = analysis_model_id if analysis_model_id in self._models else None

    def list(self) -> list[ModelConfig]:
        return list(self._models.values())

    def get(self, model_id: str) -> ModelConfig | None:
        return self._models.get(model_id)

    def get_analysis_model_id(self) -> str | None:
        return self._analysis_model_id
