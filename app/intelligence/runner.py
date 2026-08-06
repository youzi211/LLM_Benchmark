from __future__ import annotations

import os
import threading
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from app.core.models import ModelConfig, utc_now
from app.intelligence.config_store import EvalScopeConfigStore
from app.intelligence.evalscope_direct import (
    DEFAULT_DATASETS,
    EvalScopeIntelligenceExecutor,
    dataset_metadata,
    judge_config_status,
    local_dataset_metadata,
)
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
IN_PROCESS_EVALSCOPE = "in-process"


class IntelligenceExecutor(Protocol):
    def run(
        self,
        *,
        task_id: str,
        model: str,
        api_url: str,
        api_key: str,
        datasets: list[str],
        limit: int | None = None,
        eval_batch_size: int | None = None,
        generation_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...


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


def _endpoint_url(model: ModelConfig) -> str:
    base = model.base_url.rstrip("/")
    if model.protocol == "chat_completions":
        return base if base.endswith("/chat/completions") else f"{base}/chat/completions"
    if model.protocol == "responses":
        return base if base.endswith("/responses") else f"{base}/responses"
    raise ValueError(f"unsupported_protocol:{model.protocol}")


class IntelligenceRunner:
    def __init__(
        self,
        *,
        model_store: ModelStore | None = None,
        task_store: IntelligenceTaskStore | None = None,
        config_store: EvalScopeConfigStore | None = None,
        executor: IntelligenceExecutor | None = None,
        reports_dir: Path | None = None,
        run_in_background: bool = True,
    ):
        self.model_store = model_store or ModelStore()
        self.task_store = task_store or IntelligenceTaskStore()
        self.config_store = config_store or EvalScopeConfigStore()
        self.config: EvalScopeConfig = self.config_store.load()
        self.executor = executor or EvalScopeIntelligenceExecutor(self.config)
        self.reports_dir = reports_dir or Path(os.getenv("LLM_BENCHMARK_REPORTS_DIR", "reports"))
        self.run_in_background = run_in_background

    def _model(self, model_id: str) -> ModelConfig:
        model = self.model_store.get(model_id)
        if model is None:
            raise ValueError(f"model_not_found:{model_id}")
        if not model.enabled:
            raise ValueError(f"model_disabled:{model_id}")
        return model

    async def submit_default(self, model_id: str) -> IntelligenceTask:
        return await self.submit_custom(model_id=model_id, datasets=list(DEFAULT_DATASETS))

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
            evalscope_task_id=None,
            model_id=model.id,
            model_config_name=model.name,
            upstream_model_name=model.model,
            evalscope_base_url=IN_PROCESS_EVALSCOPE,
            datasets=datasets,
            status="pending",
            progress="任务已创建，等待本地 EvalScope 执行",
            raw_submit_response={"mode": IN_PROCESS_EVALSCOPE, "task_id": None, "status": "pending", "datasets": datasets},
        )
        self.task_store.save(task)
        self._start(
            task.task_id,
            model=model.model,
            api_url=_endpoint_url(model),
            api_key=model.api_key or "EMPTY",
            datasets=datasets,
            limit=limit,
            eval_batch_size=eval_batch_size,
            generation_config=generation_config,
        )
        return self.task_store.get(task.task_id) or task

    def _start(self, task_id: str, **kwargs: Any) -> None:
        if self.run_in_background:
            thread = threading.Thread(target=self._execute, args=(task_id,), kwargs=kwargs, daemon=True)
            thread.start()
        else:
            self._execute(task_id, **kwargs)

    def _execute(
        self,
        task_id: str,
        *,
        model: str,
        api_url: str,
        api_key: str,
        datasets: list[str],
        limit: int | None,
        eval_batch_size: int | None,
        generation_config: dict[str, Any] | None,
    ) -> None:
        task = self.task_store.get(task_id)
        if task is None:
            return
        task.status = "running"
        task.progress = "正在通过 Python 包直接执行 EvalScope 能力评测"
        task.updated_at = utc_now()
        self.task_store.save(task)
        try:
            raw_result = self.executor.run(
                task_id=task.task_id,
                model=model,
                api_url=api_url,
                api_key=api_key,
                datasets=datasets,
                limit=limit,
                eval_batch_size=eval_batch_size,
                generation_config=generation_config,
            )
            task.raw_result = raw_result
            metadata = self._local_dataset_metadata()
            task.normalized_result = self._normalize(task, raw_result, metadata)
            task.status = _coerce_status(raw_result.get("status"), "completed")
            if raw_result.get("datasets") and isinstance(raw_result["datasets"], list):
                task.datasets = [str(item) for item in raw_result["datasets"]]
            task.completed_at = _parse_dt(raw_result.get("completed_at")) or utc_now()
            task.evalscope_task_id = raw_result.get("task_id") or task.evalscope_task_id or task.task_id
            task.progress = "能力评测完成" if task.status == "completed" else "能力评测失败"
            report_path = write_intelligence_report(task, self.reports_dir, judge_status=self._judge_status())
            task.report_path = str(report_path)
        except Exception as exc:
            task.status = "failed"
            task.error = _safe_error(exc)
            task.progress = f"能力评测失败：{task.error['message']}"
            task.completed_at = utc_now()
            report_path = write_intelligence_report(task, self.reports_dir, judge_status=self._judge_status())
            task.report_path = str(report_path)
        finally:
            task.updated_at = utc_now()
            self.task_store.save(task)

    async def refresh_status(self, task_id: str) -> IntelligenceTask | None:
        return self.task_store.get(task_id)

    async def fetch_result(self, task_id: str) -> IntelligenceTask | None:
        task = self.task_store.get(task_id)
        if task is None:
            return None
        if task.status in TERMINAL_STATUSES and not task.report_path:
            report_path = write_intelligence_report(task, self.reports_dir, judge_status=self._judge_status())
            task.report_path = str(report_path)
            task.updated_at = utc_now()
            self.task_store.save(task)
        return task

    def _local_dataset_metadata(self) -> dict[str, dict[str, Any]]:
        data = dataset_metadata(self.config)
        datasets = data.get("datasets", {}) if isinstance(data, dict) else {}
        return datasets if isinstance(datasets, dict) else {}

    def _judge_status(self) -> dict[str, Any]:
        return judge_config_status(self.config)

    def local_datasets(self) -> dict[str, Any]:
        return local_dataset_metadata(self.config)

    def datasets(self) -> dict[str, Any]:
        return dataset_metadata(self.config)

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
            evalscope_task_id=raw_result.get("task_id") or task.evalscope_task_id or task.task_id,
            model=raw_result.get("model") or task.upstream_model_name,
            datasets=[str(item) for item in (raw_result.get("datasets") or task.datasets)],
            status=raw_result.get("status") or task.status,
            dataset_results=dataset_results,
            category_summaries=self._category_summaries(dataset_results),
            report_table=raw_result.get("report_table"),
            error=redact_text(str(raw_result.get("error") or raw_result.get("errors"))) if (raw_result.get("error") or raw_result.get("errors")) else None,
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
