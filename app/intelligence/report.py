from __future__ import annotations

import os
from pathlib import Path

from app.intelligence.schemas import IntelligenceNormalizedResult, IntelligenceTask
from app.reports.markdown import redact_text


def _cell(value) -> str:
    return redact_text(str(value if value is not None else "")).replace("|", r"\|").replace("\r\n", " ").replace("\n", " ")


def _score(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.4f}"


def write_intelligence_report(task: IntelligenceTask, reports_dir: Path | None = None, judge_status: dict | None = None) -> Path:
    reports_dir = reports_dir or Path(os.getenv("LLM_BENCHMARK_REPORTS_DIR", "reports"))
    date_part = task.created_at.strftime("%Y-%m-%d")
    path = reports_dir / "intelligence" / date_part / f"{task.task_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)

    result: IntelligenceNormalizedResult | None = task.normalized_result
    lines: list[str] = []
    lines.append(f"# 大模型智力评测报告 - {task.task_id}")
    lines.append("")
    lines.append("## 0. 一眼看懂")
    lines.append("")
    lines.append(f"- 当前状态：`{task.status}`")
    lines.append(f"- 本地模型配置：`{task.model_id}` / `{task.model_config_name or '-'}`")
    lines.append(f"- 上游模型名称：`{task.upstream_model_name or '-'}`")
    lines.append(f"- EvalScope 任务 ID：`{task.evalscope_task_id or '-'}`")
    if task.progress:
        lines.append(f"- EvalScope 进度：{task.progress}")
    if result and result.dataset_results:
        scored = [item.score for item in result.dataset_results if item.score is not None]
        if scored:
            avg = sum(scored) / len(scored)
            lines.append(f"- 已获取 {len(result.dataset_results)} 个数据集结果，其中 {len(scored)} 个带分数，平均分：`{avg:.4f}`。")
        else:
            lines.append(f"- 已获取 {len(result.dataset_results)} 个数据集结果，但未提取到统一 score 字段。")
    elif task.status in {"pending", "running"}:
        lines.append("- 评测仍在执行中，当前报告只包含任务状态，完成后重新获取结果会生成完整报告。")
    elif task.error:
        lines.append(f"- 任务异常：{_cell(task.error.get('message') or task.error)}")
    else:
        lines.append("- 暂无可展示的评测结果。")
    lines.append("")

    lines.append("## 1. 任务概览")
    lines.append("")
    lines.append(f"- 本地任务 ID：`{task.task_id}`")
    lines.append(f"- EvalScope 地址：`{_cell(task.evalscope_base_url)}`")
    lines.append(f"- 数据集：`{', '.join(task.datasets) if task.datasets else '-'}`")
    lines.append(f"- 创建时间：`{task.created_at}`")
    lines.append(f"- 更新时间：`{task.updated_at}`")
    if task.completed_at:
        lines.append(f"- 完成时间：`{task.completed_at}`")
    lines.append("")

    lines.append("## 2. Judge 状态提示")
    lines.append("")
    if judge_status:
        configured = bool(judge_status.get("configured") or judge_status.get("judge_configured"))
        required_datasets = judge_status.get("required_datasets") if isinstance(judge_status.get("required_datasets"), list) else []
        lines.append(f"- 本次是否需要 Judge：`{bool(required_datasets)}`")
        if required_datasets:
            lines.append(f"- 需要 Judge 的数据集：`{_cell(', '.join(str(item) for item in required_datasets))}`")
        lines.append(f"- Judge 是否配置：`{configured}`")
        if judge_status.get("model_id") or judge_status.get("judge_model"):
            lines.append(f"- Judge 模型：`{_cell(judge_status.get('model_id') or judge_status.get('judge_model'))}`")
        if judge_status.get("model_config_id"):
            lines.append(f"- Judge 模型配置 ID：`{_cell(judge_status.get('model_config_id'))}`")
        if judge_status.get("source"):
            lines.append(f"- Judge 来源：`{_cell(judge_status.get('source'))}`")
        if required_datasets and not configured:
            lines.append("- 注意：本次包含需要 LLM Judge 的数据集，但未解析到可用 Judge；新任务提交阶段会阻止这种配置错误。")
        elif not required_datasets:
            lines.append("- 提示：本次数据集不依赖 LLM Judge。")
    else:
        lines.append("- 未获取到 Judge 状态；如评测包含需要 Judge 的数据集，请人工确认本系统已配置 Judge 模型。")
    lines.append("")

    lines.append("## 3. 数据集分数表")
    lines.append("")
    lines.append("| 数据集 | 展示名 | 分类 | 需要 Judge | Score |")
    lines.append("|---|---|---|---|---:|")
    if result and result.dataset_results:
        for item in result.dataset_results:
            lines.append(
                f"| `{_cell(item.dataset)}` | {_cell(item.pretty_name or item.dataset)} | {_cell(', '.join(item.categories) or '-')} | "
                f"{_cell(item.needs_judge)} | {_score(item.score)} |"
            )
    else:
        lines.append("| - | - | - | - | - |")
    lines.append("")

    lines.append("## 4. 能力维度汇总")
    lines.append("")
    lines.append("| 能力维度 | 数据集数 | 有分数数据集数 | 平均 Score |")
    lines.append("|---|---:|---:|---:|")
    if result and result.category_summaries:
        for item in result.category_summaries:
            lines.append(f"| {_cell(item.category)} | {item.dataset_count} | {item.scored_dataset_count} | {_score(item.average_score)} |")
    else:
        lines.append("| - | 0 | 0 | - |")
    lines.append("")

    lines.append("## 5. 原始结果定位")
    lines.append("")
    raw_output_dir = task.raw_output_dir
    if not raw_output_dir and isinstance(task.raw_result, dict):
        candidate = task.raw_result.get("outputs_dir")
        if isinstance(candidate, str):
            raw_output_dir = candidate
    lines.append("- `normalized_result` 只保留页面、总览和摘要报告所需的分数与分类汇总；完整 EvalScope 返回不会重复嵌入本报告。")
    lines.append(f"- EvalScope 原始输出目录：`{_cell(raw_output_dir or '-')}`")
    lines.append(f"- 完整任务结果 API：`/api/intelligence/tasks/{_cell(task.task_id)}/result`（返回任务级 `raw_result` 与 `raw_output_dir`）。")
    lines.append(f"- 本 Markdown 报告 API：`/api/intelligence/reports/{_cell(task.task_id)}`。")
    lines.append("")

    path.write_text(redact_text("\n".join(lines)), encoding="utf-8")
    return path
