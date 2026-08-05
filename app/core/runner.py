from __future__ import annotations

import os
from datetime import timezone
from pathlib import Path
from typing import Callable

from app.adapters.base import BaseAdapter, create_adapter
from app.core.models import MetricResult, TaskResult, utc_now
from app.core.registry import resolve_metric_ids
from app.core.statuses import SUPPORTED_PROTOCOLS
from app.metrics.probes import (
    run_concurrency_probe,
    run_connectivity_probe,
    run_context_length_probe,
    run_error_handling_probe,
    run_output_length_probe,
    run_stream_probe,
    run_usage_probe,
)
from app.reports.analyzer import ReportAnalyzer
from app.reports.facts import build_report_fact_pack
from app.reports.markdown import write_markdown_report
from app.storage.model_store import ModelStore
from app.storage.task_store import TaskStore
from app.utils.ids import new_task_id
from app.utils.timing import elapsed_ms, now_monotonic


class TaskRunner:
    def __init__(
        self,
        model_store: ModelStore | None = None,
        task_store: TaskStore | None = None,
        reports_dir: Path | None = None,
        adapter_factory: Callable | None = None,
    ):
        self.model_store = model_store or ModelStore()
        self.task_store = task_store or TaskStore()
        self.reports_dir = reports_dir or Path(os.getenv("LLM_BENCHMARK_REPORTS_DIR", "reports"))
        self.adapter_factory = adapter_factory or create_adapter

    async def run(self, model_id: str, plan_id: str = "gateway_baseline_v1", metric_ids: list[str] | None = None) -> TaskResult:
        started_at = utc_now()
        start = now_monotonic()
        resolved = resolve_metric_ids(plan_id, metric_ids)
        result = TaskResult(task_id=new_task_id(), status="completed", model_id=model_id, plan_id=plan_id, metric_ids=resolved, started_at=started_at)
        model = self.model_store.get(model_id)
        if model is None:
            result.status = "error"
            result.error = {"code": "model_not_found", "message": f"Model config not found: {model_id}"}
            result.finished_at = utc_now()
            result.duration_ms = elapsed_ms(start)
            self.task_store.save(result)
            return result
        if not model.enabled:
            result.status = "error"
            result.error = {"code": "model_disabled", "message": f"Model config is disabled: {model_id}"}
            result.finished_at = utc_now()
            result.duration_ms = elapsed_ms(start)
            self.task_store.save(result)
            return result
        result.model_config_name = model.name
        result.upstream_model_name = model.model
        result.protocol = model.protocol

        if model.protocol not in SUPPORTED_PROTOCOLS:
            result.status = "error"
            result.error = {"code": "invalid_protocol", "message": f"Unsupported protocol: {model.protocol}"}
            result.finished_at = utc_now()
            result.duration_ms = elapsed_ms(start)
            self.task_store.save(result)
            return result

        adapter = self.adapter_factory(model)
        selected = set(resolved)
        metric_results: list[MetricResult] = []

        if "connectivity" in selected:
            metric_results.append(await run_connectivity_probe(adapter))
        if "token_usage_accuracy" in selected:
            metric_results.append(await run_usage_probe(adapter))
        if "latency_breakdown" in selected or "stream_spec" in selected:
            latency, spec = await run_stream_probe(adapter)
            if "latency_breakdown" in selected:
                metric_results.append(latency)
            if "stream_spec" in selected:
                metric_results.append(spec)
        if "output_length" in selected:
            metric_results.append(await run_output_length_probe(adapter, model))
        if "context_length" in selected:
            metric_results.append(await run_context_length_probe(adapter, model))
        if "error_handling" in selected:
            metric_results.append(await run_error_handling_probe(model, self.adapter_factory))
        if "concurrency" in selected or "rate_limit" in selected:
            concurrency, rate_limit = await run_concurrency_probe(adapter, model)
            if "concurrency" in selected:
                metric_results.append(concurrency)
            if "rate_limit" in selected:
                metric_results.append(rate_limit)

        order = {metric_id: index for index, metric_id in enumerate(resolved)}
        metric_results.sort(key=lambda item: order.get(item.metric_id, 999))
        result.results = metric_results
        result.finished_at = utc_now()
        result.duration_ms = elapsed_ms(start)
        facts = build_report_fact_pack(result)
        analysis = await ReportAnalyzer(model_store=self.model_store, adapter_factory=self.adapter_factory).analyze(facts)
        result.analysis_model_id = analysis.analysis_model_id
        result.analysis = analysis.model_dump(mode="json")
        report_path = write_markdown_report(result, self.reports_dir, facts=facts, analysis=analysis)
        result.report_path = str(report_path)
        self.task_store.save(result)
        return result
