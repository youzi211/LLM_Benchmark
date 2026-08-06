from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from app.api.routes_intelligence import router as intelligence_router
from app.api.routes_metrics import router as metrics_router
from app.api.routes_models import router as models_router
from app.api.routes_reports import router as reports_router
from app.api.routes_tasks import router as tasks_router

app = FastAPI(title="LLM Benchmark", version="0.1.0")


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"error": {"code": "http_error", "message": str(exc.detail), "details": {}}})


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(models_router, prefix="/api")
app.include_router(metrics_router, prefix="/api")
app.include_router(intelligence_router, prefix="/api")
app.include_router(tasks_router, prefix="/api")
app.include_router(reports_router, prefix="/api")
