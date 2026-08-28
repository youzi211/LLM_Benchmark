from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes_evalscope import router as evalscope_router
from app.api.routes_intelligence import router as intelligence_router
from app.api.routes_jobs import router as jobs_router
from app.api.routes_metrics import router as metrics_router
from app.api.routes_overview import router as overview_router
from app.api.routes_models import router as models_router
from app.api.routes_reports import router as reports_router
from app.api.routes_stress import router as stress_router
from app.api.routes_suites import router as suites_router
from app.api.routes_tasks import router as tasks_router
from app.jobs.executor import shutdown_job_executor
from app.suites.scheduler import start_scheduler, stop_scheduler

WEB_DIR = Path(__file__).resolve().parent / "web"
WEB_VUE_DIR = Path(__file__).resolve().parent / "web_vue"

app = FastAPI(title="LLM Benchmark", version="0.1.0")


def _mount_optional_static(application: FastAPI, url_path: str, directory: Path, name: str) -> bool:
    """Mount ``directory`` at ``url_path`` only when it exists on disk.

    The Vue rewrite keeps its build output under ``app/web_vue`` so the service can
    expose it under ``/ui-vue`` in parallel with the legacy ``/ui`` page. When the
    directory is absent (e.g. before the Vue build has been run or while only
    shipping server-side changes) the mount is skipped instead of crashing the
    FastAPI app at import time. Returns ``True`` if the mount was added.
    """

    if directory.is_dir():
        application.mount(url_path, StaticFiles(directory=str(directory), html=True), name=name)
        return True
    return False


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"error": {"code": "http_error", "message": str(exc.detail), "details": {}}})


@app.get("/", include_in_schema=False)
def ui_home():
    return RedirectResponse(url="/ui/")


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(models_router, prefix="/api")
app.include_router(metrics_router, prefix="/api")
app.include_router(overview_router, prefix="/api")
app.include_router(evalscope_router, prefix="/api")
app.include_router(intelligence_router, prefix="/api")
app.include_router(jobs_router, prefix="/api")
app.include_router(tasks_router, prefix="/api")
app.include_router(reports_router, prefix="/api")
app.include_router(stress_router, prefix="/api")
app.include_router(suites_router, prefix="/api")
app.mount("/ui", StaticFiles(directory=WEB_DIR, html=True), name="ui")
_mount_optional_static(app, "/ui-vue", WEB_VUE_DIR, name="ui-vue")


@app.on_event("startup")
async def startup_scheduler():
    start_scheduler()


@app.on_event("shutdown")
async def shutdown_scheduler():
    stop_scheduler()
    await shutdown_job_executor()
