from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ReportTaskFacts(BaseModel):
    task_id: str
    model_id: str
    model_config_name: str | None = None
    upstream_model_name: str | None = None
    protocol: str | None = None
    plan_id: str
    duration_ms: float | None = None


class ReportStatusCounts(BaseModel):
    total: int = 0
    completed: int = 0
    error: int = 0
    skipped: int = 0


class ReportRawExcerpt(BaseModel):
    label: str
    data: Any


class ReportMetricFact(BaseModel):
    metric_id: str
    metric_name: str | None = None
    status: str
    summary: str
    core_observation: str
    suggested_focus: str
    key_facts: dict[str, Any] = Field(default_factory=dict)
    important_raw_excerpt: list[ReportRawExcerpt] = Field(default_factory=list)


class ReportFactPack(BaseModel):
    task: ReportTaskFacts
    status_counts: ReportStatusCounts
    metric_facts: list[ReportMetricFact] = Field(default_factory=list)


class ReportAnalysisMetricNote(BaseModel):
    metric_id: str
    note: str
    severity: Literal["info", "low", "medium", "high"] = "info"


class ReportAnalysis(BaseModel):
    analysis_status: Literal["completed", "skipped", "error"]
    analysis_model_id: str | None = None
    one_sentence_summary: str | None = None
    overall_assessment: str | None = None
    key_findings: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    recommended_next_steps: list[str] = Field(default_factory=list)
    metric_notes: list[ReportAnalysisMetricNote] = Field(default_factory=list)
    error_message: str | None = None
    raw_excerpt: str | None = None


def skipped_analysis(message: str) -> ReportAnalysis:
    return ReportAnalysis(
        analysis_status="skipped",
        one_sentence_summary=message,
        overall_assessment=message,
    )


def errored_analysis(
    message: str,
    analysis_model_id: str | None = None,
    raw_excerpt: str | None = None,
) -> ReportAnalysis:
    return ReportAnalysis(
        analysis_status="error",
        analysis_model_id=analysis_model_id,
        one_sentence_summary="报告分析过程出现错误。",
        overall_assessment=message,
        error_message=message,
        raw_excerpt=raw_excerpt,
    )
