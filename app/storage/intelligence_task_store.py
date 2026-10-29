from __future__ import annotations

import heapq
import os
from collections.abc import Iterator
from pathlib import Path

from app.intelligence.schemas import IntelligenceTask
from app.storage.file_utils import read_json_file, write_json_file_atomic


class IntelligenceTaskStore:
    def __init__(self, directory: Path | None = None):
        self.directory = directory or (Path(os.getenv("LLM_BENCHMARK_DATA_DIR", "data")) / "intelligence_tasks")

    def _path(self, task_id: str) -> Path:
        return self.directory / f"{task_id}.json"

    def save(self, task: IntelligenceTask) -> IntelligenceTask:
        write_json_file_atomic(self._path(task.task_id), task.model_dump(mode="json"))
        return task

    def get(self, task_id: str) -> IntelligenceTask | None:
        path = self._path(task_id)
        if not path.exists():
            return None
        return IntelligenceTask.model_validate(read_json_file(path, {}))

    def iter_tasks(self) -> Iterator[IntelligenceTask]:
        if not self.directory.exists():
            return
        for path in self.directory.glob("intel_task_*.json"):
            try:
                yield IntelligenceTask.model_validate(read_json_file(path, {}))
            except Exception:
                continue

    def list(self, limit: int | None = 50) -> list[IntelligenceTask]:
        key = lambda item: (item.created_at, item.task_id)
        if limit is None:
            return sorted(self.iter_tasks(), key=key, reverse=True)
        return heapq.nlargest(limit, self.iter_tasks(), key=key)
