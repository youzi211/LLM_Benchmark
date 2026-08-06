from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.api.errors import api_error
from app.overview.report import build_overview_report, write_overview_markdown
from app.overview.schemas import OverviewReportRequest
from app.storage.overview_report_store import OverviewReportStore

router = APIRouter(prefix="/overview", tags=["overview"])


@router.post("/reports")
def create_overview_report(request: OverviewReportRequest):
    try:
        report = build_overview_report(request)
    except ValueError as exc:
        raise api_error(400, "invalid_overview_report_request", str(exc))
    write_overview_markdown(report)
    return OverviewReportStore().save(report)


@router.get("/reports")
def list_overview_reports(limit: int = 50):
    return OverviewReportStore().list(limit=limit)


@router.get("/reports/{overview_id}")
def get_overview_report(overview_id: str):
    report = OverviewReportStore().get(overview_id)
    if report is None:
        raise api_error(404, "overview_report_not_found", f"Overview report not found: {overview_id}")
    return report


@router.get("/reports/{overview_id}/markdown")
def get_overview_report_markdown(overview_id: str):
    report = OverviewReportStore().get(overview_id)
    if report is None or not report.report_path:
        raise api_error(404, "overview_report_not_found", f"Overview report not found: {overview_id}")
    path = Path(report.report_path)
    if not path.exists():
        raise api_error(404, "overview_report_not_found", f"Overview report not found: {overview_id}")
    return FileResponse(path, media_type="text/markdown; charset=utf-8", filename=path.name)
