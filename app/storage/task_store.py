from __future__ import annotations

import os
from pathlib import Path

from app.core.models import TaskResult
from app.storage.file_utils import read_json_file, write_json_file_atomic


class TaskStore:
    def __init__(self, directory: Path | None = None):
        self.directory = directory or (Path(os.getenv("LLM_BENCHMARK_DATA_DIR", "data")) / "tasks")

    def _path(self, task_id: str) -> Path:
        return self.directory / f"{task_id}.json"

    def save(self, result: TaskResult) -> TaskResult:
        write_json_file_atomic(self._path(result.task_id), result.model_dump(mode="json"))
        return result

    def get(self, task_id: str) -> TaskResult | None:
        path = self._path(task_id)
        if not path.exists():
            return None
        return TaskResult.model_validate(read_json_file(path, {}))

    def list(self, limit: int = 100) -> list[TaskResult]:
        if not self.directory.exists():
            return []
        results: list[TaskResult] = []
        for path in self.directory.glob("task_*.json"):
            try:
                results.append(TaskResult.model_validate(read_json_file(path, {})))
            except Exception:
                continue
        results.sort(key=lambda item: item.started_at, reverse=True)
        return results[:limit]
