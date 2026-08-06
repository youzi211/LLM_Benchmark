from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.reports.markdown import redact_text
from app.stress.schemas import StressTask


def _cell(value: Any) -> str:
    return redact_text(str(value if value is not None else "-")).replace("|", r"\|").replace("\n", " ")


def _fmt(value: Any, suffix: str = "") -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.4f}{suffix}"
    return f"{value}{suffix}"


def _json_block(data: Any) -> str:
    return redact_text(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def write_stress_report(task: StressTask, reports_dir: Path | None = None) -> Path:
    reports_dir = reports_dir or Path(os.getenv("LLM_BENCHMARK_REPORTS_DIR", "reports"))
    date_part = task.created_at.strftime("%Y-%m-%d")
    path = reports_dir / "stress" / date_part / f"{task.task_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)

    result = task.normalized_result
    lines: list[str] = []
    lines.append(f"# 模型压测报告 - {task.task_id}")
    lines.append("")
    lines.append("## 0. 一眼看懂")
    lines.append("")
    if result:
        summary = result.summary or {}
        lines.append(f"- 最大无失败并发档位：`{_cell(summary.get('max_success_parallel'))}`")
        lines.append(f"- 最高请求吞吐：`{_cell(summary.get('best_req_throughput'))}` req/s")
        if summary.get("best_output_throughput") is not None:
            lines.append(f"- 最高输出吞吐：`{_cell(summary.get('best_output_throughput'))}` tok/s")
        lines.append(f"- 首次出现失败/限流的并发档位：`{_cell(summary.get('first_error_parallel'))}`")
        if result.errors:
            lines.append(f"- 异常记录数：`{len(result.errors)}`，请查看异常摘要。")
        elif result.runs:
            lines.append("- 未在标准化结果中发现异常记录。")
        else:
            lines.append("- 未提取到并发档位结果，请查看原始结果附录。")
    elif task.status in {"pending", "running"}:
        lines.append("- 任务仍在执行中，暂未生成压测结果。")
    elif task.error:
        lines.append(f"- 任务异常：{_cell(task.error.get('message') or task.error)}")
    else:
        lines.append("- 暂无压测结果。")

    lines.append("")
    lines.append("## 1. 任务概览")
    lines.append("")
    lines.append(f"- 本地任务 ID：`{task.task_id}`")
    lines.append(f"- EvalScope 压测任务 ID：`{task.evalscope_stress_task_id or '-'}`")
    lines.append(f"- 模型配置：`{task.model_id}` / `{task.model_config_name or '-'}`")
    lines.append(f"- 上游模型名称：`{task.upstream_model_name or '-'}`")
    lines.append(f"- 协议：`{task.protocol or '-'}`")
    lines.append(f"- 当前状态：`{task.status}`")
    if task.progress:
        lines.append(f"- 进度：{_cell(task.progress)}")
    lines.append(f"- EvalScope 地址：`{_cell(task.evalscope_base_url)}`")
    lines.append(f"- 创建时间：`{task.created_at}`")
    lines.append(f"- 更新时间：`{task.updated_at}`")
    if task.completed_at:
        lines.append(f"- 完成时间：`{task.completed_at}`")

    lines.append("")
    lines.append("## 2. 压测配置")
    lines.append("")
    cfg = dict(task.request_config or {})
    cfg.pop("api_key", None)
    for key in ["api", "url", "parallel", "number", "rate", "stream", "dataset", "tokenizer_path", "min_prompt_length", "max_prompt_length", "min_tokens", "max_tokens", "prefix_length", "dataset_args", "extra_args"]:
        if key in cfg:
            lines.append(f"- `{key}`：`{_cell(cfg[key])}`")

    lines.append("")
    lines.append("## 3. 并发档位结果")
    lines.append("")
    lines.append("| 并发 | 请求数 | 成功 | 失败 | 成功率 | RPS | 输出吞吐(tok/s) | 平均延迟(s) | P95延迟(s) | 平均TTFT(ms) | P95 TTFT(ms) | 平均TPOT(ms) |")
    lines.append("|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    if result and result.runs:
        for run in result.runs:
            lines.append(
                "| "
                + " | ".join([
                    _fmt(run.parallel),
                    _fmt(run.total or run.number),
                    _fmt(run.success),
                    _fmt(run.failed),
                    _fmt(run.success_rate),
                    _fmt(run.request_throughput),
                    _fmt(run.output_throughput),
                    _fmt(run.avg_latency_seconds),
                    _fmt(run.p95_latency_seconds),
                    _fmt(run.avg_ttft_ms),
                    _fmt(run.p95_ttft_ms),
                    _fmt(run.avg_tpot_ms),
                ])
                + " |"
            )
    else:
        lines.append("| - | - | - | - | - | - | - | - | - | - | - | - |")

    lines.append("")
    lines.append("## 4. 异常摘要")
    lines.append("")
    if result and result.errors:
        for item in result.errors:
            lines.append(f"- `{_cell(item.get('type') or item.get('code') or 'error')}`：{_cell(item.get('message') or item)}")
    elif task.error:
        lines.append(f"- `{_cell(task.error.get('type'))}`：{_cell(task.error.get('message'))}")
    else:
        lines.append("- 未发现标准化异常。")

    lines.append("")
    lines.append("## 5. 原始结果附录（已脱敏）")
    lines.append("")
    lines.append("```json")
    lines.append(_json_block(result.raw_result if result else (task.raw_result or task.raw_status_response or task.raw_submit_response or {})))
    lines.append("```")
    lines.append("")

    path.write_text(redact_text("\n".join(lines)), encoding="utf-8")
    return path
