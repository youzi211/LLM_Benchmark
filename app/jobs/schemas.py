from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from app.core.models import utc_now

JobStatus = Literal["queued", "running", "completed", "failed", "interrupted"]
JobType = Literal["suite", "intelligence", "stress"]


def new_job_id() -> str:
    return f"job_{utc_now().strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:8]}"


class JobRecord(BaseModel):
    job_id: str = Field(default_factory=new_job_id)
    job_type: JobType
    target_id: str | None = None
    status: JobStatus = "queued"
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: dict[str, Any] | None = None
