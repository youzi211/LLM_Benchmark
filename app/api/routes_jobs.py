from __future__ import annotations

from fastapi import APIRouter

from app.api.errors import api_error
from app.jobs.store import JobStore

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("")
def list_jobs(limit: int = 50):
    return JobStore().list(limit=limit)


@router.get("/{job_id}")
def get_job(job_id: str):
    job = JobStore().get(job_id)
    if job is None:
        raise api_error(404, "job_not_found", f"Job not found: {job_id}")
    return job
