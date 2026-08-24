from __future__ import annotations

import os
from pathlib import Path

from app.core.models import utc_now
from app.jobs.schemas import JobRecord
from app.storage.file_utils import read_json_file, write_json_file_atomic


class JobStore:
    def __init__(self, directory: Path | None = None):
        self.directory = directory or (Path(os.getenv("LLM_BENCHMARK_DATA_DIR", "data")) / "jobs")

    def _path(self, job_id: str) -> Path:
        return self.directory / f"{job_id}.json"

    def save(self, job: JobRecord) -> JobRecord:
        job.updated_at = utc_now()
        write_json_file_atomic(self._path(job.job_id), job.model_dump(mode="json"))
        return job

    def get(self, job_id: str) -> JobRecord | None:
        path = self._path(job_id)
        if not path.exists():
            return None
        return JobRecord.model_validate(read_json_file(path, {}))

    def list(self, limit: int = 50) -> list[JobRecord]:
        if not self.directory.exists():
            return []
        jobs: list[JobRecord] = []
        for path in self.directory.glob("job_*.json"):
            try:
                jobs.append(JobRecord.model_validate(read_json_file(path, {})))
            except Exception:
                continue
        jobs.sort(key=lambda item: (item.created_at, item.job_id), reverse=True)
        return jobs[:limit]
