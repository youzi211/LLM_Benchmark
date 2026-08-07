from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any

from app.intelligence.schemas import EvalScopeConfig
from app.reports.markdown import redact_text

DEFAULT_DATASETS = [
    "humaneval",
    "mbpp",
    "humaneval_plus",
    "mbpp_plus",
    "live_code_bench",
    "gsm8k",
    "math_500",
    "mmlu_pro",
    "ceval",
    "bbh",
]
DEFAULT_EVAL_BATCH_SIZE = 10
DEFAULT_GENERATION_CONFIG = {"temperature": 0.0, "max_tokens": 8192}

LLM_JUDGE_DATASETS = {
    "simple_qa",
    "chinese_simpleqa",
    "truthful_qa",
    "alpaca_eval",
    "arena_hard",
    "general_qa",
    "general_vqa",
    "halu_eval",
    "halueval",
    "longbench_v2",
}

CODE_EXECUTION_DATASETS = {
    "humaneval",
    "humaneval_plus",
    "mbpp",
    "mbpp_plus",
    "live_code_bench",
}

_DATASET_META: dict[str, dict[str, Any]] = {
    "humaneval": {"pretty_name": "HumanEval", "description": "代码生成评测", "categories": ["Code"], "needs_judge": False},
    "humaneval_plus": {"pretty_name": "HumanEval+", "description": "HumanEval 增强版", "categories": ["Code"], "needs_judge": False},
    "mbpp": {"pretty_name": "MBPP", "description": "基础编程题评测", "categories": ["Code"], "needs_judge": False},
    "mbpp_plus": {"pretty_name": "MBPP+", "description": "MBPP 增强版", "categories": ["Code"], "needs_judge": False},
    "live_code_bench": {"pretty_name": "LiveCodeBench", "description": "实时代码评测", "categories": ["Code"], "needs_judge": False},
    "gsm8k": {"pretty_name": "GSM8K", "description": "小学数学多步推理", "categories": ["Math", "Reasoning"], "needs_judge": False},
    "math_500": {"pretty_name": "MATH-500", "description": "数学竞赛题", "categories": ["Math", "Reasoning"], "needs_judge": False},
    "mmlu_pro": {"pretty_name": "MMLU-Pro", "description": "综合知识增强评测", "categories": ["Knowledge"], "needs_judge": False},
    "ceval": {"pretty_name": "C-Eval", "description": "中文综合能力评测", "categories": ["Knowledge", "Chinese"], "needs_judge": False},
    "bbh": {"pretty_name": "BBH", "description": "Big-Bench Hard 复杂推理", "categories": ["Reasoning"], "needs_judge": False},
    "mmlu": {"pretty_name": "MMLU", "description": "大规模多任务语言理解", "categories": ["Knowledge"], "needs_judge": False},
    "cmmlu": {"pretty_name": "CMMLU", "description": "中文多任务理解", "categories": ["Knowledge", "Chinese"], "needs_judge": False},
    "ifeval": {"pretty_name": "IFEval", "description": "指令遵循评测", "categories": ["Instruction"], "needs_judge": False},
    "simple_qa": {"pretty_name": "SimpleQA", "description": "事实问答，需要 LLM Judge", "categories": ["QA", "Knowledge"], "needs_judge": True},
    "chinese_simpleqa": {"pretty_name": "Chinese SimpleQA", "description": "中文事实问答，需要 LLM Judge", "categories": ["QA", "Knowledge", "Chinese"], "needs_judge": True},
    "truthful_qa": {"pretty_name": "TruthfulQA", "description": "真实性评测", "categories": ["QA", "Truthfulness"], "needs_judge": True},
    "alpaca_eval": {"pretty_name": "AlpacaEval", "description": "指令遵循，需要 LLM Judge", "categories": ["Instruction"], "needs_judge": True},
    "arena_hard": {"pretty_name": "Arena-Hard", "description": "对话质量，需要 LLM Judge", "categories": ["Instruction"], "needs_judge": True},
    "longbench_v2": {"pretty_name": "LongBench v2", "description": "长上下文评测", "categories": ["Long Context"], "needs_judge": True},
}


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


def dataset_metadata(config: EvalScopeConfig) -> dict[str, Any]:
    datasets = {name: dict(meta) for name, meta in _DATASET_META.items()}
    local = local_dataset_metadata(config).get("datasets", {})
    for name, meta in local.items():
        row = datasets.setdefault(name, {})
        row.update(meta)
    return {"total": len(datasets), "default_datasets": list(DEFAULT_DATASETS), "datasets": datasets}


def local_dataset_metadata(config: EvalScopeConfig) -> dict[str, Any]:
    root = datasets_root(config)
    datasets: dict[str, dict[str, Any]] = {}
    if root.exists():
        for child in sorted(root.iterdir()):
            if not child.is_dir():
                continue
            base = dict(_DATASET_META.get(child.name, {}))
            base.update({"name": child.name, "local_path": str(child), "available_local": True})
            datasets[child.name] = base
    return {"total": len(datasets), "datasets_dir": str(root), "datasets": datasets}


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

        for dataset in datasets:
            cfg_data = self._task_config_data(
                model=model,
                api_url=api_url,
                api_key=api_key or "EMPTY",
                dataset=dataset,
                local_paths=local_paths,
                limit=limit,
                eval_batch_size=eval_batch_size,
                generation_config=generation_config,
                work_dir=str(output_base / dataset),
                judge_model_args=judge_model_args,
            )
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
            except Exception as exc:
                errors.append({"dataset": dataset, "message": redact_text(str(exc)), "type": exc.__class__.__name__})
                if not self.config.ignore_dataset_errors:
                    raise

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
    ) -> dict[str, Any]:
        dataset_args: dict[str, dict[str, Any]] = {}
        if dataset in local_paths:
            dataset_args[dataset] = {"local_path": local_paths[dataset]}
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
            data["use_sandbox"] = True
            data["sandbox_type"] = self.config.sandbox_type or "docker"
            if self.config.sandbox_manager_config:
                data["sandbox_manager_config"] = dict(self.config.sandbox_manager_config)
        if dataset in LLM_JUDGE_DATASETS and judge_model_args:
            data["judge_strategy"] = "llm"
            data["judge_model_args"] = judge_model_args
            data["judge_worker_num"] = self.config.judge_worker_num
        return data

    def _local_paths(self) -> dict[str, str]:
        root = datasets_root(self.config)
        if not root.exists():
            return {}
        return {child.name: str(child) for child in root.iterdir() if child.is_dir()}

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
