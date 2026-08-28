from __future__ import annotations

import os
from pathlib import Path

from app.storage.file_utils import read_json_file, write_json_file_atomic
from app.stress.schemas import StressTask
from app.utils.json_sanitize import make_json_safe


class StressTaskStore:
    def __init__(self, directory: Path | None = None):
        self.directory = directory or (Path(os.getenv("LLM_BENCHMARK_DATA_DIR", "data")) / "stress_tasks")

    def _path(self, task_id: str) -> Path:
        return self.directory / f"{task_id}.json"

    def save(self, task: StressTask) -> StressTask:
        write_json_file_atomic(self._path(task.task_id), make_json_safe(task.model_dump(mode="json")))
        return task

    def get(self, task_id: str) -> StressTask | None:
        path = self._path(task_id)
        if not path.exists():
            return None
        return StressTask.model_validate(make_json_safe(read_json_file(path, {})))

    def list(self, limit: int = 50) -> list[StressTask]:
        if not self.directory.exists():
            return []
        tasks: list[StressTask] = []
        for path in self.directory.glob("stress_task_*.json"):
            try:
                tasks.append(StressTask.model_validate(make_json_safe(read_json_file(path, {}))))
            except Exception:
                continue
        tasks.sort(key=lambda item: (item.created_at, item.task_id), reverse=True)
        return tasks[:limit]
