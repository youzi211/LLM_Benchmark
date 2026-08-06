from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.models import ModelConfig, utc_now
from app.intelligence.config_store import EvalScopeConfigStore
from app.intelligence.evalscope_client import EvalScopeClient, EvalScopeClientError
from app.intelligence.report import write_intelligence_report
from app.intelligence.schemas import (
    EvalScopeConfig,
    IntelligenceCategorySummary,
    IntelligenceDatasetResult,
    IntelligenceNormalizedResult,
    IntelligenceTask,
)
from app.reports.markdown import redact_text
from app.storage.intelligence_task_store import IntelligenceTaskStore
from app.storage.model_store import ModelStore

TERMINAL_STATUSES = {"completed", "failed"}
ALLOWED_STATUSES = {"pending", "running", "completed", "failed"}


def _coerce_status(value: Any, fallback: str = "pending") -> str:
    text = str(value or fallback)
    return text if text in ALLOWED_STATUSES else fallback


def new_intelligence_task_id() -> str:
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"intel_task_{stamp}_{uuid4().hex[:8]}"


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _safe_error(exc: Exception) -> dict[str, Any]:
    return {"message": redact_text(str(exc)), "type": exc.__class__.__name__}


class IntelligenceRunner:
    def __init__(
        self,
        *,
        model_store: ModelStore | None = None,
        task_store: IntelligenceTaskStore | None = None,
        config_store: EvalScopeConfigStore | None = None,
        client: EvalScopeClient | None = None,
        reports_dir: Path | None = None,
    ):
        self.model_store = model_store or ModelStore()
        self.task_store = task_store or IntelligenceTaskStore()
        self.config_store = config_store or EvalScopeConfigStore()
        self.config: EvalScopeConfig = self.config_store.load()
        self.client = client or EvalScopeClient(self.config)
        self.reports_dir = reports_dir or Path(os.getenv("LLM_BENCHMARK_REPORTS_DIR", "reports"))

    def _model(self, model_id: str) -> ModelConfig:
        model = self.model_store.get(model_id)
        if model is None:
            raise ValueError(f"model_not_found:{model_id}")
        if not model.enabled:
            raise ValueError(f"model_disabled:{model_id}")
        return model

    async def submit_default(self, model_id: str) -> IntelligenceTask:
        model = self._model(model_id)
        task = IntelligenceTask(
            task_id=new_intelligence_task_id(),
            model_id=model.id,
            model_config_name=model.name,
            upstream_model_name=model.model,
            evalscope_base_url=self.config.base_url,
            status="pending",
            progress="任务已创建",
        )
        try:
            response = await self.client.submit_default(model=model.model, api_url=model.base_url, api_key=model.api_key)
            self._apply_submit_response(task, response)
        except Exception as exc:
            task.status = "failed"
            task.error = _safe_error(exc)
            task.progress = f"错误: {task.error['message']}"
        task.updated_at = utc_now()
        self.task_store.save(task)
        return task

    async def submit_custom(
        self,
        *,
        model_id: str,
        datasets: list[str],
        limit: int | None = None,
        eval_batch_size: int | None = None,
        generation_config: dict[str, Any] | None = None,
    ) -> IntelligenceTask:
        model = self._model(model_id)
        task = IntelligenceTask(
            task_id=new_intelligence_task_id(),
            model_id=model.id,
            model_config_name=model.name,
            upstream_model_name=model.model,
            evalscope_base_url=self.config.base_url,
            datasets=datasets,
            status="pending",
            progress="任务已创建",
        )
        try:
            response = await self.client.submit_custom(
                model=model.model,
                api_url=model.base_url,
                api_key=model.api_key,
                datasets=datasets,
                limit=limit,
                eval_batch_size=eval_batch_size,
                generation_config=generation_config,
            )
            self._apply_submit_response(task, response)
        except Exception as exc:
            task.status = "failed"
            task.error = _safe_error(exc)
            task.progress = f"错误: {task.error['message']}"
        task.updated_at = utc_now()
        self.task_store.save(task)
        return task

    def _apply_submit_response(self, task: IntelligenceTask, response: dict[str, Any]) -> None:
        task.raw_submit_response = response
        task.evalscope_task_id = response.get("task_id") or task.evalscope_task_id
        task.status = _coerce_status(response.get("status"), "pending")
        task.message = response.get("message")
        task.progress = response.get("progress") or task.progress or task.message
        if response.get("datasets") and isinstance(response["datasets"], list):
            task.datasets = [str(item) for item in response["datasets"]]

    async def refresh_status(self, task_id: str) -> IntelligenceTask | None:
        task = self.task_store.get(task_id)
        if task is None:
            return None
        if not task.evalscope_task_id:
            return task
        try:
            status = await self.client.task_status(task.evalscope_task_id)
            task.raw_status_response = status
            task.status = _coerce_status(status.get("status"), task.status)
            task.progress = status.get("progress") or task.progress
            if status.get("datasets") and isinstance(status["datasets"], list):
                task.datasets = [str(item) for item in status["datasets"]]
            if task.status in TERMINAL_STATUSES:
                task.completed_at = _parse_dt(status.get("completed_at") or status.get("updated_at")) or task.completed_at
            task.updated_at = utc_now()
            self.task_store.save(task)
        except Exception as exc:
            task.error = _safe_error(exc)
            task.updated_at = utc_now()
            self.task_store.save(task)
        return task

    async def fetch_result(self, task_id: str) -> IntelligenceTask | None:
        task = await self.refresh_status(task_id)
        if task is None:
            return None
        if task.status not in TERMINAL_STATUSES or not task.evalscope_task_id:
            return task
        try:
            raw_result = await self.client.task_result(task.evalscope_task_id)
            task.raw_result = raw_result
            metadata = await self._local_dataset_metadata()
            task.normalized_result = self._normalize(task, raw_result, metadata)
            task.status = _coerce_status(raw_result.get("status"), task.status)
            if raw_result.get("datasets") and isinstance(raw_result["datasets"], list):
                task.datasets = [str(item) for item in raw_result["datasets"]]
            task.completed_at = _parse_dt(raw_result.get("completed_at")) or task.completed_at
            judge_status = await self._judge_status()
            report_path = write_intelligence_report(task, self.reports_dir, judge_status=judge_status)
            task.report_path = str(report_path)
            task.updated_at = utc_now()
            self.task_store.save(task)
        except Exception as exc:
            task.error = _safe_error(exc)
            task.updated_at = utc_now()
            self.task_store.save(task)
        return task

    async def _local_dataset_metadata(self) -> dict[str, dict[str, Any]]:
        try:
            data = await self.client.local_datasets()
            datasets = data.get("datasets", {}) if isinstance(data, dict) else {}
            return datasets if isinstance(datasets, dict) else {}
        except Exception:
            return {}

    async def _judge_status(self) -> dict[str, Any] | None:
        try:
            return await self.client.judge_config()
        except Exception:
            return None

    def _normalize(
        self,
        task: IntelligenceTask,
        raw_result: dict[str, Any],
        metadata: dict[str, dict[str, Any]],
    ) -> IntelligenceNormalizedResult:
        dataset_results: list[IntelligenceDatasetResult] = []
        for row in raw_result.get("results") or []:
            if not isinstance(row, dict):
                continue
            dataset = str(row.get("dataset") or row.get("dataset_name") or "unknown")
            report = row.get("report") if isinstance(row.get("report"), dict) else {}
            meta = metadata.get(dataset, {}) if isinstance(metadata.get(dataset, {}), dict) else {}
            categories = meta.get("categories") if isinstance(meta.get("categories"), list) else []
            dataset_results.append(
                IntelligenceDatasetResult(
                    dataset=dataset,
                    pretty_name=meta.get("pretty_name") or report.get("dataset_name") or dataset,
                    categories=[str(item) for item in categories],
                    needs_judge=meta.get("needs_judge"),
                    score=report.get("score") if isinstance(report.get("score"), (int, float)) else None,
                    metrics=report.get("metrics") if isinstance(report.get("metrics"), list) else [],
                    raw_report=report,
                )
            )
        return IntelligenceNormalizedResult(
            task_id=task.task_id,
            evalscope_task_id=raw_result.get("task_id") or task.evalscope_task_id,
            model=raw_result.get("model") or task.upstream_model_name,
            datasets=[str(item) for item in (raw_result.get("datasets") or task.datasets)],
            status=raw_result.get("status") or task.status,
            dataset_results=dataset_results,
            category_summaries=self._category_summaries(dataset_results),
            report_table=raw_result.get("report_table"),
            error=redact_text(str(raw_result.get("error"))) if raw_result.get("error") else None,
            created_at=_parse_dt(raw_result.get("created_at")),
            completed_at=_parse_dt(raw_result.get("completed_at")),
        )

    def _category_summaries(self, dataset_results: list[IntelligenceDatasetResult]) -> list[IntelligenceCategorySummary]:
        buckets: dict[str, list[IntelligenceDatasetResult]] = defaultdict(list)
        uncategorized: list[IntelligenceDatasetResult] = []
        for item in dataset_results:
            if item.categories:
                for category in item.categories:
                    buckets[category].append(item)
            else:
                uncategorized.append(item)
        if uncategorized:
            buckets["未分类"].extend(uncategorized)
        summaries: list[IntelligenceCategorySummary] = []
        for category in sorted(buckets):
            rows = buckets[category]
            scores = [item.score for item in rows if item.score is not None]
            summaries.append(
                IntelligenceCategorySummary(
                    category=category,
                    dataset_count=len(rows),
                    scored_dataset_count=len(scores),
                    average_score=(sum(scores) / len(scores)) if scores else None,
                )
            )
        return summaries
