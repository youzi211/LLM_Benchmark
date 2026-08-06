from __future__ import annotations

import os
from pathlib import Path

from app.overview.schemas import OverviewReport
from app.storage.file_utils import read_json_file, write_json_file_atomic


class OverviewReportStore:
    def __init__(self, directory: Path | None = None):
        self.directory = directory or (Path(os.getenv("LLM_BENCHMARK_DATA_DIR", "data")) / "overview_reports")

    def _path(self, overview_id: str) -> Path:
        return self.directory / f"{overview_id}.json"

    def save(self, report: OverviewReport) -> OverviewReport:
        write_json_file_atomic(self._path(report.overview_id), report.model_dump(mode="json"))
        return report

    def get(self, overview_id: str) -> OverviewReport | None:
        path = self._path(overview_id)
        if not path.exists():
            return None
        return OverviewReport.model_validate(read_json_file(path, {}))

    def list(self, limit: int = 50) -> list[OverviewReport]:
        if not self.directory.exists():
            return []
        reports: list[OverviewReport] = []
        for path in self.directory.glob("overview_report_*.json"):
            try:
                reports.append(OverviewReport.model_validate(read_json_file(path, {})))
            except Exception:
                continue
        reports.sort(key=lambda item: (item.created_at, item.overview_id), reverse=True)
        return reports[:limit]
