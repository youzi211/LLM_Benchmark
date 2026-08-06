from __future__ import annotations

import os
from pathlib import Path

from app.intelligence.schemas import EvalScopeConfig
from app.storage.file_utils import read_json_file, write_json_file_atomic


class EvalScopeConfigStore:
    def __init__(self, path: Path | None = None):
        self.path = path or (Path(os.getenv("LLM_BENCHMARK_DATA_DIR", "data")) / "evalscope.json")

    def load(self) -> EvalScopeConfig:
        data = read_json_file(self.path, {})
        if not isinstance(data, dict):
            data = {}
        return EvalScopeConfig.model_validate(data)

    def save(self, config: EvalScopeConfig) -> EvalScopeConfig:
        write_json_file_atomic(self.path, config.model_dump(mode="json"))
        return config
