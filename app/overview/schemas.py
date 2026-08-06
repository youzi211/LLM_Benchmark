from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from app.core.models import utc_now


class OverviewReportRequest(BaseModel):
    """引用已有任务生成统一总览报告。

    第一版不自动触发新评测，只把已有的网关验收、EvalScope 能力评测、
    EvalScope 压测任务组合成一份中文导航摘要。
    """

    model_id: str | None = None
    gateway_task_id: str | None = None
    intelligence_task_id: str | None = None
    stress_task_id: str | None = None
    title: str | None = None

    @model_validator(mode="after")
    def require_at_least_one_task(self) -> "OverviewReportRequest":
        if not any([self.gateway_task_id, self.intelligence_task_id, self.stress_task_id]):
            raise ValueError("at least one task id is required")
        return self


class OverviewComponent(BaseModel):
    kind: str
    title: str
    task_id: str | None = None
    status: str = "missing"
    summary: str = "未提供任务。"
    report_path: str | None = None
    report_endpoint: str | None = None
    highlights: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class OverviewReport(BaseModel):
    overview_id: str = Field(default_factory=lambda: f"overview_report_{utc_now().strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:8]}")
    title: str = "模型评测总览报告"
    model_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    gateway_task_id: str | None = None
    intelligence_task_id: str | None = None
    stress_task_id: str | None = None
    components: list[OverviewComponent] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    report_path: str | None = None
