from __future__ import annotations

import copy
import json
import os
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import httpx

from app.evalscope_defaults import (
    CODE_EXECUTION_DATASETS,
    DATASET_METADATA,
    DEFAULT_EVAL_BATCH_SIZE,
    DEFAULT_GENERATION_CONFIG,
    DEFAULT_INTELLIGENCE_DATASET_ARGS,
    DEFAULT_INTELLIGENCE_DATASETS,
    LLM_JUDGE_DATASETS,
)
from app.intelligence.schemas import EvalScopeConfig
from app.reports.markdown import redact_text

DEFAULT_DATASETS = list(DEFAULT_INTELLIGENCE_DATASETS)
_DATASET_META: dict[str, dict[str, Any]] = {name: dict(meta) for name, meta in DATASET_METADATA.items()}


class EvalScopeDirectError(RuntimeError):
    pass


def outputs_root(config: EvalScopeConfig) -> Path:
    configured = config.outputs_dir or os.getenv("LLM_BENCHMARK_EVALSCOPE_OUTPUTS_DIR") or "outputs/evalscope"
    return Path(configured)


def datasets_root(config: EvalScopeConfig) -> Path:
    configured = config.datasets_dir or os.getenv("LLM_BENCHMARK_EVALSCOPE_DATASETS_DIR") or "data/evalscope_datasets"
    return Path(configured)


def evalscope_health() -> dict[str, Any]:
    try:
        import evalscope  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on optional local install
        return {"status": "error", "mode": "in_process", "error": redact_text(str(exc))}
    return {"status": "ok", "mode": "in_process", "evalscope_version": getattr(evalscope, "__version__", None)}


def sandbox_health(config: EvalScopeConfig, *, timeout_seconds: float = 3.0, deep: bool = False) -> dict[str, Any]:
    """Best-effort liveness probe for the configured EvalScope sandbox.

    The default mode verifies that the configured sandbox manager is reachable.
    When ``deep`` is true and a remote manager is configured, it also creates a
    short-lived sandbox, executes a trivial shell command, and deletes it. This
    mirrors the EvalScope code-execution path closely enough to catch missing
    Docker/shell-tool problems before users submit jobs.
    """

    engine = config.sandbox_type or "docker"
    manager_config = dict(config.sandbox_manager_config or {})
    if not config.sandbox_enabled:
        return {"status": "disabled", "engine": engine, "message": "sandbox is disabled"}

    base_url = manager_config.get("base_url") or manager_config.get("url") or manager_config.get("endpoint")
    if isinstance(base_url, str) and base_url.strip():
        root = base_url.strip().rstrip("/")
        candidates = [f"{root}/health", f"{root}/sandboxes"]
        errors: list[str] = []
        for url in candidates:
            try:
                response = httpx.get(url, timeout=timeout_seconds)
            except Exception as exc:  # pragma: no cover - depends on external service
                errors.append(f"{url}: {redact_text(str(exc))}")
                continue
            if 200 <= response.status_code < 300:
                payload: dict[str, Any] | None = None
                try:
                    parsed = response.json()
                    payload = parsed if isinstance(parsed, dict) else {"items": parsed}
                except Exception:
                    payload = None
                result: dict[str, Any] = {
                    "status": "ok",
                    "engine": engine,
                    "base_url": root,
                    "http_status": response.status_code,
                    "checked_url": url,
                    "detail": payload,
                }
                if deep:
                    result["execution"] = _remote_sandbox_execution_smoke(
                        root,
                        engine,
                        manager_config,
                        timeout_seconds=timeout_seconds,
                    )
                    if result["execution"].get("status") != "ok":
                        result["status"] = "error"
                        result["error"] = result["execution"].get("error") or "sandbox execution smoke failed"
                return result
            errors.append(f"{url}: HTTP {response.status_code}")
        return {"status": "error", "engine": engine, "base_url": root, "error": "; ".join(errors[-2:])}

    if engine == "docker":
        try:
            result = subprocess.run(
                ["docker", "info"],
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except Exception as exc:  # pragma: no cover - depends on host docker install
            return {"status": "error", "engine": engine, "error": redact_text(str(exc))}
        if result.returncode == 0:
            return {"status": "ok", "engine": engine, "message": "docker daemon is reachable"}
        detail = (result.stderr or result.stdout or "docker info failed").strip()
        return {"status": "error", "engine": engine, "error": redact_text(detail)}

    return {
        "status": "unknown",
        "engine": engine,
        "message": "no remote base_url/url/endpoint configured and no built-in probe for this sandbox engine",
    }


def _remote_sandbox_execution_smoke(
    root: str,
    engine: str,
    manager_config: dict[str, Any],
    *,
    timeout_seconds: float,
) -> dict[str, Any]:
    sandbox_id: str | None = None
    headers = {}
    api_key = manager_config.get("api_key")
    if isinstance(api_key, str) and api_key:
        headers["X-API-Key"] = api_key
    try:
        request_timeout = max(timeout_seconds, 30.0)
        create_response = httpx.post(
            f"{root}/sandbox/create",
            params={"sandbox_type": engine},
            json={
                "image": manager_config.get("image") or "python:3.11-slim",
                "working_dir": "/sandbox",
                "tools_config": ["shell_executor"],
            },
            headers=headers,
            timeout=request_timeout,
        )
        if create_response.status_code != 200:
            return {
                "status": "error",
                "stage": "create",
                "http_status": create_response.status_code,
                "error": redact_text(create_response.text[:500]),
            }
        data = create_response.json()
        sandbox_id = str(data.get("sandbox_id") or "")
        if not sandbox_id:
            return {"status": "error", "stage": "create", "error": "sandbox_id missing in response"}

        execute_response = httpx.post(
            f"{root}/sandbox/tool/execute",
            json={
                "sandbox_id": sandbox_id,
                "tool_name": "shell_executor",
                "parameters": {"command": "echo LLM_BENCHMARK_SANDBOX_OK", "timeout": 10},
            },
            headers=headers,
            timeout=request_timeout,
        )
        if execute_response.status_code != 200:
            return {
                "status": "error",
                "stage": "execute",
                "http_status": execute_response.status_code,
                "sandbox_id": sandbox_id,
                "error": redact_text(execute_response.text[:500]),
            }
        executed = execute_response.json()
        output = str(executed.get("output") or "")
        if executed.get("status") != "success" or "LLM_BENCHMARK_SANDBOX_OK" not in output:
            return {"status": "error", "stage": "execute", "sandbox_id": sandbox_id, "error": redact_text(str(executed)[:500])}
        return {"status": "ok", "stage": "execute", "sandbox_id": sandbox_id, "output": "LLM_BENCHMARK_SANDBOX_OK"}
    except Exception as exc:  # pragma: no cover - depends on external service
        return {"status": "error", "stage": "exception", "error": redact_text(str(exc))}
    finally:
        if sandbox_id:
            try:
                httpx.delete(f"{root}/sandbox/{sandbox_id}", headers=headers, timeout=max(timeout_seconds, 30.0))
            except Exception:
                pass


def dataset_metadata(config: EvalScopeConfig) -> dict[str, Any]:
    datasets = {name: dict(meta) for name, meta in _DATASET_META.items()}
    local = local_dataset_metadata(config).get("datasets", {})
    for name, meta in local.items():
        row = datasets.setdefault(name, {})
        row.update(meta)
    for name, row in datasets.items():
        configured_subsets = _configured_subset_list(config, name)
        if configured_subsets:
            row["configured_subset_list"] = configured_subsets
    return {"total": len(datasets), "default_datasets": list(DEFAULT_DATASETS), "datasets": datasets}


def _configured_subset_list(config: EvalScopeConfig, dataset: str) -> list[str]:
    args = copy.deepcopy(DEFAULT_INTELLIGENCE_DATASET_ARGS.get(dataset, {}))
    args.update(copy.deepcopy(config.dataset_args.get(dataset, {})))
    subset_list = args.get("subset_list")
    if isinstance(subset_list, (list, tuple)):
        return [str(item) for item in subset_list if str(item)]
    return []


def _local_subset_names(dataset_dir: Path) -> list[str]:
    """Return local EvalScope subset directories for a dataset, if present."""
    subsets: list[str] = []
    try:
        children = sorted(dataset_dir.iterdir(), key=lambda item: item.name)
    except OSError:
        return subsets
    for child in children:
        if not child.is_dir() or child.name.startswith(".") or child.name == "__pycache__":
            continue
        subsets.append(child.name)
    return subsets


def local_dataset_metadata(config: EvalScopeConfig) -> dict[str, Any]:
    root = datasets_root(config)
    datasets: dict[str, dict[str, Any]] = {}
    if root.exists():
        for child in sorted(root.iterdir()):
            if not child.is_dir() or child.name.startswith(".") or child.name not in _DATASET_META:
                continue
            base = dict(_DATASET_META.get(child.name, {}))
            subsets = _local_subset_names(child)
            configured_subsets = _configured_subset_list(config, child.name)
            base.update(
                {
                    "name": child.name,
                    "local_path": str(child),
                    "available_local": True,
                    "subsets": subsets,
                    "subset_count": len(subsets),
                    "has_subsets": bool(subsets),
                }
            )
            if configured_subsets:
                base["configured_subset_list"] = configured_subsets
            datasets[child.name] = base
    default_datasets = [name for name in DEFAULT_DATASETS if name in datasets]
    return {"total": len(datasets), "default_datasets": default_datasets, "datasets_dir": str(root), "datasets": datasets}


def datasets_requiring_judge(datasets: list[str]) -> list[str]:
    return [dataset for dataset in datasets if dataset in LLM_JUDGE_DATASETS]


def judge_config_status(
    config: EvalScopeConfig,
    *,
    configured: bool = False,
    model_config_id: str | None = None,
    model_name: str | None = None,
    source: str | None = None,
    required_datasets: list[str] | None = None,
    missing_reason: str | None = None,
) -> dict[str, Any]:
    status: dict[str, Any] = {
        "configured": configured,
        "mode": "in_process",
        "model_config_id": model_config_id or config.judge_model_config_id or None,
        "model_id": model_name or None,
        "source": source,
        "required_datasets": required_datasets or [],
        "generation_config": config.judge_generation_config,
        "judge_worker_num": config.judge_worker_num,
    }
    if missing_reason:
        status["missing_reason"] = missing_reason
    return status


def _to_plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return {str(k): _to_plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_plain(v) for v in value]
    return value


PROGRESS_FILE_NAME = "progress.json"


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _read_progress_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    processed = _coerce_int(data.get("processed_count"))
    total = _coerce_int(data.get("total_count"))
    percent = _coerce_float(data.get("percent"))
    if total is not None and total > 0 and processed is not None:
        percent = round(max(0, min(processed, total)) / total * 100, 2)
    return {
        "status": str(data.get("status") or "running"),
        "pipeline": str(data.get("pipeline") or "eval"),
        "processed_count": processed,
        "total_count": total,
        "percent": percent,
        "updated_at": data.get("updated_at"),
    }


def _latest_progress_file(work_dir: Path) -> Path | None:
    candidates: list[Path] = []
    direct = work_dir / PROGRESS_FILE_NAME
    if direct.exists():
        candidates.append(direct)
    if work_dir.exists():
        try:
            for child in work_dir.iterdir():
                if child.is_dir():
                    nested = child / PROGRESS_FILE_NAME
                    if nested.exists():
                        candidates.append(nested)
        except OSError:
            return None
    if not candidates:
        return None
    try:
        return max(candidates, key=lambda item: item.stat().st_mtime)
    except OSError:
        return candidates[-1]


def read_evalscope_dataset_progress(work_dir: str | Path, dataset: str) -> dict[str, Any] | None:
    progress_file = _latest_progress_file(Path(work_dir))
    if progress_file is None:
        return None
    progress = _read_progress_json(progress_file)
    if progress is None:
        return None
    progress["dataset"] = dataset
    return progress


def summarize_evalscope_task_progress(output_root: str | Path, datasets: list[str]) -> dict[str, Any] | None:
    if not datasets:
        return None
    root = Path(output_root)
    dataset_progress: list[dict[str, Any]] = []
    current_index = 1
    current: dict[str, Any] | None = None
    finished_count = 0
    finished_datasets: set[str] = set()

    for index, dataset in enumerate(datasets, start=1):
        progress = read_evalscope_dataset_progress(root / dataset, dataset)
        if progress is None:
            if current is None:
                current_index = index
                current = {"dataset": dataset, "status": "pending", "processed_count": 0, "total_count": None, "percent": None}
            continue
        dataset_progress.append(progress)
        status = str(progress.get("status") or "running")
        percent = _coerce_float(progress.get("percent"))
        if status in {"completed", "error", "failed"} or (percent is not None and percent >= 100):
            finished_count += 1
            finished_datasets.add(dataset)
        elif current is None:
            current_index = index
            current = progress

    if current is None:
        if dataset_progress:
            current_index = min(finished_count, len(datasets)) or 1
            current = dataset_progress[-1]
        else:
            current = {"dataset": datasets[0], "status": "pending", "processed_count": 0, "total_count": None, "percent": None}

    current_dataset = str(current.get("dataset") or datasets[min(current_index - 1, len(datasets) - 1)])
    current_percent = _coerce_float(current.get("percent"))
    current_fraction = (current_percent / 100) if current_percent is not None else 0.0
    if str(current.get("status") or "") == "completed":
        current_fraction = 1.0
    overall_units = finished_count if current_dataset in finished_datasets else finished_count + current_fraction
    overall_percent = round((overall_units / len(datasets)) * 100, 2)
    overall_percent = max(0.0, min(overall_percent, 100.0))

    processed = _coerce_int(current.get("processed_count"))
    total = _coerce_int(current.get("total_count"))
    status = str(current.get("status") or "running")
    if total and processed is not None:
        sample_text = f"{processed}/{total}"
        if current_percent is not None:
            sample_text += f"（{current_percent:.1f}%）"
    else:
        sample_text = "准备中" if status == "pending" else status
    prefix = "等待能力评测开始" if status == "pending" else "能力评测进行中"
    message = f"{prefix}：{current_dataset} {sample_text}，数据集 {current_index}/{len(datasets)}"

    return {
        "status": status,
        "current_dataset": current_dataset,
        "dataset_index": current_index,
        "dataset_total": len(datasets),
        "processed_count": processed,
        "total_count": total,
        "percent": current_percent,
        "overall_percent": overall_percent,
        "message": message,
        "updated_at": current.get("updated_at"),
        "datasets": dataset_progress,
    }


class EvalScopeIntelligenceExecutor:
    def __init__(self, config: EvalScopeConfig):
        self.config = config

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
        dataset_args: dict[str, dict[str, Any]] | None = None,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        try:
            from evalscope import TaskConfig, run_task  # type: ignore
        except Exception as exc:  # pragma: no cover - depends on optional local install
            raise EvalScopeDirectError(f"evalscope_import_failed:{redact_text(str(exc))}") from exc

        started = datetime.now().isoformat()
        output_base = outputs_root(self.config) / "intelligence" / task_id
        output_base.mkdir(parents=True, exist_ok=True)
        local_paths = self._local_paths()
        results: list[dict[str, Any]] = []
        report_map: dict[str, Any] = {}
        errors: list[dict[str, Any]] = []

        for dataset_index, dataset in enumerate(datasets, start=1):
            dataset_work_dir = output_base / dataset
            cfg_data = self._task_config_data(
                model=model,
                api_url=api_url,
                api_key=api_key or "EMPTY",
                dataset=dataset,
                local_paths=local_paths,
                limit=limit,
                eval_batch_size=eval_batch_size,
                generation_config=generation_config,
                work_dir=str(dataset_work_dir),
                judge_model_args=judge_model_args,
                user_dataset_args=dataset_args,
            )

            def emit(progress: dict[str, Any]) -> None:
                if progress_callback is None:
                    return
                payload = summarize_evalscope_task_progress(output_base, datasets) or {
                    "status": progress.get("status") or "running",
                    "current_dataset": dataset,
                    "dataset_index": dataset_index,
                    "dataset_total": len(datasets),
                    "processed_count": progress.get("processed_count"),
                    "total_count": progress.get("total_count"),
                    "percent": progress.get("percent"),
                    "overall_percent": round(((dataset_index - 1) / len(datasets)) * 100, 2),
                    "message": f"能力评测进行中：{dataset}，数据集 {dataset_index}/{len(datasets)}",
                    "updated_at": progress.get("updated_at"),
                    "datasets": [],
                }
                try:
                    progress_callback(payload)
                except Exception:
                    pass

            stop_monitor = threading.Event()

            def monitor_progress() -> None:
                while not stop_monitor.wait(1.0):
                    progress = read_evalscope_dataset_progress(dataset_work_dir, dataset)
                    if progress is not None:
                        emit(progress)

            emit({"status": "running"})
            monitor = threading.Thread(target=monitor_progress, name=f"evalscope-progress-{task_id}-{dataset}", daemon=True)
            monitor.start()
            try:
                result = run_task(task_cfg=TaskConfig(**cfg_data))
                plain = _to_plain(result)
                if isinstance(plain, dict):
                    if dataset in plain:
                        report = plain[dataset]
                    elif len(plain) == 1:
                        report = next(iter(plain.values()))
                    else:
                        report = plain
                else:
                    report = {"value": plain}
                report_map[dataset] = report
                results.append({"dataset": dataset, "report": report})
                emit({"status": "completed", "processed_count": 1, "total_count": 1, "percent": 100})
            except Exception as exc:
                emit({"status": "error"})
                errors.append({"dataset": dataset, "message": redact_text(str(exc)), "type": exc.__class__.__name__})
                if not self.config.ignore_dataset_errors:
                    raise
            finally:
                stop_monitor.set()
                monitor.join(timeout=1.0)

        status = "failed" if errors and not results else "completed"
        report_table = self._report_table(report_map)
        completed = datetime.now().isoformat()
        return {
            "task_id": task_id,
            "model": model,
            "datasets": datasets,
            "status": status,
            "results": results,
            "errors": errors,
            "report_table": report_table,
            "created_at": started,
            "completed_at": completed,
            "outputs_dir": str(output_base),
        }

    def _task_config_data(
        self,
        *,
        model: str,
        api_url: str,
        api_key: str,
        dataset: str,
        local_paths: dict[str, str],
        limit: int | None,
        eval_batch_size: int | None,
        generation_config: dict[str, Any] | None,
        work_dir: str,
        judge_model_args: dict[str, Any] | None,
        user_dataset_args: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        dataset_args = self._dataset_args(dataset=dataset, local_paths=local_paths, user_dataset_args=user_dataset_args)
        data: dict[str, Any] = {
            "model": model,
            "api_url": api_url,
            "api_key": api_key,
            "eval_type": "openai_api",
            "eval_backend": "Native",
            "datasets": [dataset],
            "dataset_args": dataset_args,
            "limit": limit,
            "eval_batch_size": eval_batch_size or DEFAULT_EVAL_BATCH_SIZE,
            "generation_config": generation_config or DEFAULT_GENERATION_CONFIG,
            "seed": 42,
            "ignore_errors": True,
            "work_dir": work_dir,
            "enable_progress_tracker": True,
        }
        if self.config.datasets_dir:
            data["dataset_dir"] = str(datasets_root(self.config))
        if dataset in CODE_EXECUTION_DATASETS:
            if not self.config.sandbox_enabled:
                raise EvalScopeDirectError(
                    f"sandbox_required:{dataset}; "
                    "EvalScope code-execution benchmarks require sandbox scoring. "
                    "Set sandbox_enabled=true and configure a local or remote sandbox manager."
                )
            data["sandbox"] = {
                "enabled": True,
                "engine": self.config.sandbox_type or "docker",
                "manager_config": dict(self.config.sandbox_manager_config or {}),
            }
        if dataset in LLM_JUDGE_DATASETS and judge_model_args:
            data["judge_strategy"] = "llm"
            data["judge_model_args"] = judge_model_args
            data["judge_worker_num"] = self.config.judge_worker_num
        return data

    def _dataset_args(self, *, dataset: str, local_paths: dict[str, str], user_dataset_args: dict[str, dict[str, Any]] | None = None) -> dict[str, dict[str, Any]]:
        args = copy.deepcopy(DEFAULT_INTELLIGENCE_DATASET_ARGS.get(dataset, {}))
        args.update(copy.deepcopy(self.config.dataset_args.get(dataset, {})))
        if user_dataset_args and dataset in user_dataset_args:
            args.update(copy.deepcopy(user_dataset_args[dataset]))
        if dataset in local_paths and not args.get("local_path"):
            args["local_path"] = local_paths[dataset]
        return {dataset: args} if args else {}

    def _local_paths(self) -> dict[str, str]:
        root = datasets_root(self.config)
        if not root.exists():
            return {}
        return {child.name: str(child) for child in root.iterdir() if child.is_dir() and child.name in _DATASET_META}

    def _report_table(self, report_map: dict[str, Any]) -> str | None:
        if not report_map:
            return None
        try:
            from evalscope.report import Report, gen_table  # type: ignore

            reports = []
            for report in report_map.values():
                if isinstance(report, dict):
                    try:
                        reports.append(Report.from_dict(report))
                    except Exception:
                        continue
            if not reports:
                return None
            table = gen_table(report_list=reports, add_overall_metric=True)
            return str(table) if table else None
        except Exception as exc:
            return f"生成 EvalScope 汇总表失败：{redact_text(str(exc))}"

