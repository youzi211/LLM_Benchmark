from __future__ import annotations

import os
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from app.core.models import ModelConfig, utc_now
from app.intelligence.config_store import EvalScopeConfigStore
from app.reports.markdown import redact_text
from app.storage.model_store import ModelStore
from app.storage.stress_task_store import StressTaskStore
from app.stress.evalscope_direct import EvalScopeStressExecutor
from app.stress.report import write_stress_report
from app.stress.schemas import (
    StressDefaultRunRequest,
    StressNormalizedResult,
    StressRemoteSubmitPayload,
    StressRunResult,
    StressTask,
)

# 压测用本地数据集目录（与智力评测的 data/evalscope_datasets 分开，避免语义混淆）。
# 仅当用户指定了本地数据集名但未显式给出 dataset_path 时自动填充。
STRESS_DATASETS_DIR = Path(os.getenv("LLM_BENCHMARK_STRESS_DATASETS_DIR", "data/stress_datasets"))

# 透传给 EvalScope perf 的字段。dataset_path 不在此列：由 _resolve_dataset_path
# 按本地数据集约定补齐，避免把占位默认值当成真实路径传给 EvalScope。
ALLOWED_OPTION_KEYS: tuple[str, ...] = (
    "parallel",
    "number",
    "dataset",
    "dataset_path",
    "stream",
    "min_prompt_length",
    "max_prompt_length",
    "min_tokens",
    "max_tokens",
    "rate",
    "tokenizer_path",
    "prefix_length",
    "dataset_args",
    "extra_args",
)

# 已知会从 ModelScope 下载的真实语料数据集。当 dataset 命中且 data/stress_datasets
# 下存在同名顶层目录或 .json 文件时，自动补 dataset_path，EvalScope 的 load_hub_dataset
# 会据此改为 local 加载（"from local" 而非 "from modelscope"），实现一次下载、永久离线复用。
# random / speed_benchmark 等不下载的内置数据集不在其中。
LOCAL_RESOLVABLE_DATASETS = frozenset(
    {
        "longalpaca",
        "openqa",
        "share_gpt_zh",
        "share_gpt_en",
        "share_gpt_zh_multi_turn",
        "share_gpt_en_multi_turn",
        "flickr8k",
        "kontext_bench",
        "swe_smith",
    }
)

TERMINAL_STATUSES = {"completed", "failed"}
ALLOWED_STATUSES = {"pending", "running", "completed", "failed"}
IN_PROCESS_EVALSCOPE = "in-process"


class StressExecutor(Protocol):
    def run(self, *, task_id: str, payload: StressRemoteSubmitPayload) -> dict[str, Any]: ...


def new_stress_task_id() -> str:
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"stress_task_{stamp}_{uuid4().hex[:8]}"


def _coerce_status(value: Any, fallback: str = "pending") -> str:
    text = str(value or fallback)
    return text if text in ALLOWED_STATUSES else fallback


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
        if base.endswith("/chat/completions"):
            return base
        return f"{base}/chat/completions"
    if model.protocol == "responses":
        if base.endswith("/responses"):
            return base
        return f"{base}/responses"
    raise ValueError(f"unsupported_protocol:{model.protocol}")


def _api_type(model: ModelConfig) -> str:
    if model.protocol == "chat_completions":
        return "openai"
    if model.protocol == "responses":
        return "openai_responses"
    raise ValueError(f"unsupported_protocol:{model.protocol}")


def _parse_parallel_number(label: str) -> tuple[int | None, int | None]:
    match = re.search(r"parallel_(\d+)_number_(\d+)", label)
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def _percentile_value(rows: Any, percentile: str, key: str) -> Any:
    if not isinstance(rows, list):
        return None
    wanted = {percentile, percentile.replace("%", ""), f"p{percentile.replace('%', '')}".lower()}
    for row in rows:
        if not isinstance(row, dict):
            continue
        label = str(row.get("percentile", "")).lower()
        if label in wanted:
            return row.get(key)
    return None


def _perf_mapping_rows(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, dict):
        return []
    rows: list[dict[str, Any]] = []
    for label, value in raw.items():
        if not isinstance(value, dict) or not isinstance(value.get("metrics"), dict):
            continue
        parallel, number = _parse_parallel_number(str(label))
        metrics = dict(value["metrics"])
        percentile_rows = (value.get("percentiles") or {}).get("rows") if isinstance(value.get("percentiles"), dict) else []
        if parallel is not None:
            metrics.setdefault("parallel", parallel)
            metrics.setdefault("concurrency", parallel)
        if number is not None:
            metrics.setdefault("number", number)
        metrics.setdefault("total", metrics.get("total_requests"))
        metrics.setdefault("success", metrics.get("succeed_requests", metrics.get("success_requests")))
        metrics.setdefault("failed", metrics.get("failed_requests"))
        metrics.setdefault("output_throughput", metrics.get("output_token_throughput"))
        metrics.setdefault("total_throughput", metrics.get("total_token_throughput"))
        metrics.setdefault("avg_latency_seconds", metrics.get("avg_latency"))
        metrics.setdefault("avg_ttft_ms", metrics.get("avg_ttft"))
        metrics.setdefault("avg_tpot_ms", metrics.get("avg_tpot"))
        metrics.setdefault("p50_latency_seconds", _percentile_value(percentile_rows, "50%", "latency"))
        metrics.setdefault("p95_latency_seconds", _percentile_value(percentile_rows, "95%", "latency"))
        metrics.setdefault("p99_latency_seconds", _percentile_value(percentile_rows, "99%", "latency"))
        metrics.setdefault("p95_ttft_ms", _percentile_value(percentile_rows, "95%", "ttft"))
        metrics.setdefault("p99_ttft_ms", _percentile_value(percentile_rows, "99%", "ttft"))
        metrics["raw"] = value
        rows.append(metrics)
    return rows


class StressRunner:
    def __init__(
        self,
        *,
        model_store: ModelStore | None = None,
        task_store: StressTaskStore | None = None,
        config_store: EvalScopeConfigStore | None = None,
        executor: StressExecutor | None = None,
        reports_dir: Path | None = None,
        run_in_background: bool = True,
    ):
        self.model_store = model_store or ModelStore()
        self.task_store = task_store or StressTaskStore()
        self.config_store = config_store or EvalScopeConfigStore()
        self.config = self.config_store.load()
        self.executor = executor or EvalScopeStressExecutor(self.config)
        self.reports_dir = reports_dir or Path(os.getenv("LLM_BENCHMARK_REPORTS_DIR", "reports"))
        self.run_in_background = run_in_background

    async def submit_default(self, model_id: str, options: StressDefaultRunRequest | None = None) -> StressTask:
        options = options or StressDefaultRunRequest(model_id=model_id)
        model = self.model_store.get(model_id)
        if model is None:
            raise ValueError(f"model_not_found:{model_id}")
        if not model.enabled:
            raise ValueError(f"model_disabled:{model_id}")

        payload = self._build_payload(model, options)
        task = StressTask(
            task_id=new_stress_task_id(),
            model_id=model.id,
            model_config_name=model.name,
            upstream_model_name=model.model,
            protocol=model.protocol,
            evalscope_base_url=IN_PROCESS_EVALSCOPE,
            request_config=self._public_request_config(payload),
            status="pending",
            progress="任务已创建，等待本地 EvalScope 执行",
        )
        task.raw_submit_response = {"mode": IN_PROCESS_EVALSCOPE, "task_id": task.task_id, "status": "pending"}
        self.task_store.save(task)
        self._start(task.task_id, payload)
        return self.task_store.get(task.task_id) or task

    def _start(self, task_id: str, payload: StressRemoteSubmitPayload) -> None:
        if self.run_in_background:
            thread = threading.Thread(target=self._execute, args=(task_id, payload), daemon=True)
            thread.start()
        else:
            self._execute(task_id, payload)

    def _execute(self, task_id: str, payload: StressRemoteSubmitPayload) -> None:
        task = self.task_store.get(task_id)
        if task is None:
            return
        task.status = "running"
        task.progress = "正在通过 Python 包直接执行 EvalScope 压测"
        task.updated_at = utc_now()
        self.task_store.save(task)
        try:
            raw_result = self.executor.run(task_id=task.task_id, payload=payload)
            task.raw_result = raw_result
            task.normalized_result = self._normalize(task, raw_result)
            task.status = _coerce_status(raw_result.get("status"), "completed")
            task.completed_at = _parse_dt(raw_result.get("completed_at")) or utc_now()
            task.progress = "压测完成" if task.status == "completed" else "压测失败"
            report_path = write_stress_report(task, self.reports_dir)
            task.report_path = str(report_path)
        except Exception as exc:
            task.status = "failed"
            task.error = _safe_error(exc)
            task.progress = f"压测失败：{task.error['message']}"
            task.completed_at = utc_now()
            report_path = write_stress_report(task, self.reports_dir)
            task.report_path = str(report_path)
        finally:
            task.updated_at = utc_now()
            self.task_store.save(task)

    def _build_payload(self, model: ModelConfig, options: StressDefaultRunRequest) -> StressRemoteSubmitPayload:
        data: dict[str, Any] = {
            "model": model.model,
            "url": _endpoint_url(model),
            "api_key": model.api_key or "EMPTY",
            "api": _api_type(model),
        }
        dataset_path = self._resolve_dataset_path(options)
        for key in ALLOWED_OPTION_KEYS:
            value = getattr(options, key, None)
            if value is None:
                # dataset_path 单独处理：用户未显式指定时，按本地数据集约定补齐，
                # 让 EvalScope 改为 local 加载；其它字段为空一律不透传。
                if key == "dataset_path" and dataset_path is not None:
                    value = dataset_path
                else:
                    continue
            data[key] = value
        return StressRemoteSubmitPayload.model_validate(data)

    def _resolve_dataset_path(self, options: StressDefaultRunRequest) -> str | None:
        """命中本地可复用数据集时补齐 dataset_path，避免每次评测都从 ModelScope 下载。

        仅当用户显式给出 dataset_path 时以用户值为准；否则当 dataset 命中
        LOCAL_RESOLVABLE_DATASETS 且本地存在同名目录或 .json 文件时自动补齐。
        """
        user_path = getattr(options, "dataset_path", None)
        if user_path:
            return user_path

        dataset = getattr(options, "dataset", None)
        if dataset not in LOCAL_RESOLVABLE_DATASETS:
            return None
        if not STRESS_DATASETS_DIR.exists():
            return None
        candidate_dir = STRESS_DATASETS_DIR / dataset
        if candidate_dir.is_dir():
            return str(candidate_dir)
        candidate_file = STRESS_DATASETS_DIR / f"{dataset}.json"
        if candidate_file.is_file():
            return str(candidate_file)
        return None

    def _public_request_config(self, payload: StressRemoteSubmitPayload) -> dict[str, Any]:
        data = payload.model_dump(mode="json")
        data.pop("api_key", None)
        return data

    async def refresh_status(self, task_id: str) -> StressTask | None:
        return self._maybe_renormalize(self.task_store.get(task_id))

    async def fetch_result(self, task_id: str) -> StressTask | None:
        task = self.task_store.get(task_id)
        if task is None:
            return None
        task = self._maybe_renormalize(task)
        if task.status in TERMINAL_STATUSES and not task.report_path:
            report_path = write_stress_report(task, self.reports_dir)
            task.report_path = str(report_path)
            task.updated_at = utc_now()
            self.task_store.save(task)
        return task

    def _maybe_renormalize(self, task: StressTask | None) -> StressTask | None:
        """对终态任务做展示回填：旧版 executor 返回的 metrics 是 pydantic 对象，
        导致持久化的 normalized_result.runs 为空（档位被解析跳过）。这里在读取时
        按 raw_result 重新标准化，让历史任务的档位表/一眼看懂也能正常显示。"""
        if task is None or task.status not in TERMINAL_STATUSES:
            return task
        if not task.raw_result:
            return task
        nr = task.normalized_result
        if nr is not None and nr.runs:
            return task
        try:
            fresh = self._normalize(task, task.raw_result)
        except Exception:  # noqa: BLE001 - 回填失败不应阻断读取
            return task
        if not fresh.runs:
            return task
        task.normalized_result = fresh
        task.updated_at = utc_now()
        try:
            report_path = write_stress_report(task, self.reports_dir)
            task.report_path = str(report_path)
        except Exception:  # noqa: BLE001 - 报告重写失败不阻断读取
            pass
        self.task_store.save(task)
        return task

    def _normalize(self, task: StressTask, raw_result: dict[str, Any]) -> StressNormalizedResult:
        raw_runs = raw_result.get("runs") or raw_result.get("results") or []
        if not raw_runs:
            raw_runs = _perf_mapping_rows(raw_result.get("raw_result"))
        if not raw_runs:
            raw_runs = _perf_mapping_rows(raw_result)
        runs: list[StressRunResult] = []
        if isinstance(raw_runs, list):
            for row in raw_runs:
                if not isinstance(row, dict):
                    continue
                runs.append(self._normalize_run(row))
        errors = raw_result.get("errors") if isinstance(raw_result.get("errors"), list) else []
        return StressNormalizedResult(
            task_id=task.task_id,
            evalscope_stress_task_id=raw_result.get("task_id") or task.evalscope_stress_task_id or task.task_id,
            model=raw_result.get("model") or task.upstream_model_name,
            status=raw_result.get("status") or task.status,
            summary=raw_result.get("summary") if isinstance(raw_result.get("summary"), dict) else self._summary_from_runs(runs),
            runs=runs,
            errors=[item for item in errors if isinstance(item, dict)],
            raw_result=raw_result,
        )

    def _normalize_run(self, row: dict[str, Any]) -> StressRunResult:
        def first(*keys: str) -> Any:
            for key in keys:
                if key in row:
                    return row[key]
            return None

        total = first("total", "total_requests", "number")
        success = first("success", "successful", "success_requests", "succeed_requests")
        success_rate = first("success_rate")
        if success_rate is None and isinstance(total, (int, float)) and total:
            success_rate = (success or 0) / total
        return StressRunResult(
            parallel=first("parallel", "concurrency"),
            number=first("number"),
            total=total,
            success=success,
            failed=first("failed", "fail", "failed_requests"),
            success_rate=success_rate,
            request_throughput=first("request_throughput", "req_throughput", "rps"),
            output_throughput=first("output_throughput", "output_token_throughput", "output_tps", "tps"),
            total_throughput=first("total_throughput", "total_token_throughput", "total_tps"),
            avg_latency_seconds=first("avg_latency_seconds", "avg_latency", "latency_avg"),
            p50_latency_seconds=first("p50_latency_seconds", "p50_latency", "latency_p50"),
            p95_latency_seconds=first("p95_latency_seconds", "p95_latency", "latency_p95"),
            p99_latency_seconds=first("p99_latency_seconds", "p99_latency", "latency_p99"),
            avg_ttft_ms=first("avg_ttft_ms", "avg_ttft", "ttft_avg"),
            p95_ttft_ms=first("p95_ttft_ms", "p95_ttft", "ttft_p95"),
            p99_ttft_ms=first("p99_ttft_ms", "p99_ttft", "ttft_p99"),
            avg_tpot_ms=first("avg_tpot_ms", "avg_tpot", "tpot_avg"),
            p95_tpot_ms=first("p95_tpot_ms", "p95_tpot", "tpot_p95"),
            p99_tpot_ms=first("p99_tpot_ms", "p99_tpot", "tpot_p99"),
            raw=row,
        )

    def _summary_from_runs(self, runs: list[StressRunResult]) -> dict[str, Any]:
        summary: dict[str, Any] = {}
        successful = [run for run in runs if run.failed in (None, 0)]
        if successful:
            summary["max_success_parallel"] = max((run.parallel or 0) for run in successful)
        throughputs = [run.request_throughput for run in runs if run.request_throughput is not None]
        if throughputs:
            summary["best_req_throughput"] = max(throughputs)
        output_throughputs = [run.output_throughput for run in runs if run.output_throughput is not None]
        if output_throughputs:
            summary["best_output_throughput"] = max(output_throughputs)
        first_error = next((run.parallel for run in runs if run.failed and run.failed > 0), None)
        summary["first_error_parallel"] = first_error
        return summary
