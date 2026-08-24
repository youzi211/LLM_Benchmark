from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from app.core.models import ModelConfig, utc_now
from app.intelligence.config_store import EvalScopeConfigStore
from app.jobs.executor import get_job_executor
from app.intelligence.evalscope_direct import (
    DEFAULT_DATASETS,
    EvalScopeIntelligenceExecutor,
    dataset_metadata,
    datasets_requiring_judge,
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
JUDGE_MODEL_CONFIG_ID_ENV = "LLM_BENCHMARK_EVALSCOPE_JUDGE_MODEL_CONFIG_ID"


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
        judge_model_args: dict[str, Any] | None = None,
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

    def _judge_candidates(self) -> list[tuple[str, str]]:
        candidates: list[tuple[str, str]] = []
        if self.config.judge_model_config_id:
            candidates.append(("evalscope_config", self.config.judge_model_config_id))
        env_model_id = os.getenv(JUDGE_MODEL_CONFIG_ID_ENV)
        if env_model_id:
            candidates.append(("environment", env_model_id.strip()))
        analysis_model_id = self.model_store.get_analysis_model_id()
        if analysis_model_id:
            candidates.append(("analysis_model", analysis_model_id))

        seen: set[str] = set()
        unique: list[tuple[str, str]] = []
        for source, model_id in candidates:
            if not model_id or model_id in seen:
                continue
            seen.add(model_id)
            unique.append((source, model_id))
        return unique

    def _resolve_judge_model(self) -> tuple[ModelConfig | None, str | None, str | None]:
        missing: list[str] = []
        disabled: list[str] = []
        for source, model_id in self._judge_candidates():
            model = self.model_store.get(model_id)
            if model is None:
                missing.append(model_id)
                continue
            if not model.enabled:
                disabled.append(model_id)
                continue
            return model, source, None
        if disabled:
            return None, None, f"configured Judge model is disabled: {', '.join(disabled)}"
        if missing:
            return None, None, f"configured Judge model not found: {', '.join(missing)}"
        return None, None, "no Judge model configured; set analysis_model_id or judge_model_config_id"

    async def submit_default(self, model_id: str, *, limit: int | None = None) -> IntelligenceTask:
        return await self.submit_custom(model_id=model_id, datasets=list(DEFAULT_DATASETS), limit=limit)

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
        required_judge_datasets = datasets_requiring_judge(datasets)
        judge_model, judge_source, judge_missing_reason = self._resolve_judge_model()
        if required_judge_datasets and judge_model is None:
            raise ValueError(f"judge_required:{', '.join(required_judge_datasets)}; {judge_missing_reason}")
        judge_model_args = None
        if judge_model is not None:
            judge_model_args = {
                "model_id": judge_model.model,
                "api_url": _endpoint_url(judge_model),
                "api_key": judge_model.api_key or "EMPTY",
                "generation_config": self.config.judge_generation_config,
            }
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
            raw_submit_response={
                "mode": IN_PROCESS_EVALSCOPE,
                "task_id": None,
                "status": "pending",
                "datasets": datasets,
                "judge": {
                    "configured": judge_model is not None,
                    "source": judge_source,
                    "model_config_id": judge_model.id if judge_model is not None else None,
                    "required_datasets": required_judge_datasets,
                },
            },
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
            judge_model_args=judge_model_args,
        )
        return self.task_store.get(task.task_id) or task

    def _start(self, task_id: str, **kwargs: Any) -> None:
        if self.run_in_background:
            get_job_executor().submit_sync(
                job_type="intelligence",
                target_id=task_id,
                payload={"task_id": task_id},
                func=lambda: self._execute(task_id, **kwargs),
            )
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
        judge_model_args: dict[str, Any] | None,
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
                judge_model_args=judge_model_args,
            )
            task.raw_result = raw_result
            task.raw_output_dir = raw_result.get("outputs_dir") if isinstance(raw_result.get("outputs_dir"), str) else None
            metadata = self._local_dataset_metadata()
            task.normalized_result = self._normalize(task, raw_result, metadata)
            task.status = _coerce_status(raw_result.get("status"), "completed")
            if raw_result.get("datasets") and isinstance(raw_result["datasets"], list):
                task.datasets = [str(item) for item in raw_result["datasets"]]
            task.completed_at = _parse_dt(raw_result.get("completed_at")) or utc_now()
            task.evalscope_task_id = raw_result.get("task_id") or task.evalscope_task_id or task.task_id
            task.progress = "能力评测完成" if task.status == "completed" else "能力评测失败"
            report_path = write_intelligence_report(task, self.reports_dir, judge_status=self._judge_status(task.datasets))
            task.report_path = str(report_path)
        except Exception as exc:
            task.status = "failed"
            task.error = _safe_error(exc)
            task.progress = f"能力评测失败：{task.error['message']}"
            task.completed_at = utc_now()
            report_path = write_intelligence_report(task, self.reports_dir, judge_status=self._judge_status(task.datasets))
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
            report_path = write_intelligence_report(task, self.reports_dir, judge_status=self._judge_status(task.datasets))
            task.report_path = str(report_path)
            task.updated_at = utc_now()
            self.task_store.save(task)
        return task

    def _local_dataset_metadata(self) -> dict[str, dict[str, Any]]:
        data = dataset_metadata(self.config)
        datasets = data.get("datasets", {}) if isinstance(data, dict) else {}
        return datasets if isinstance(datasets, dict) else {}

    def _judge_status(self, datasets: list[str] | None = None) -> dict[str, Any]:
        judge_model, source, missing_reason = self._resolve_judge_model()
        return judge_config_status(
            self.config,
            configured=judge_model is not None,
            model_config_id=judge_model.id if judge_model is not None else self.config.judge_model_config_id,
            model_name=judge_model.model if judge_model is not None else None,
            source=source,
            required_datasets=datasets_requiring_judge(datasets or []),
            missing_reason=None if judge_model is not None else missing_reason,
        )

    def judge_status(self) -> dict[str, Any]:
        return self._judge_status()

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
