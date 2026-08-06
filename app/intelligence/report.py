from __future__ import annotations

import json
import os
from pathlib import Path

from app.intelligence.schemas import IntelligenceNormalizedResult, IntelligenceTask
from app.reports.markdown import redact_text


def _cell(value) -> str:
    return redact_text(str(value if value is not None else "")).replace("|", r"\|").replace("\r\n", " ").replace("\n", " ")


def _json_block(data) -> str:
    return redact_text(json.dumps(data, ensure_ascii=False, indent=2, default=str))


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
        configured = judge_status.get("configured") or judge_status.get("judge_configured")
        lines.append(f"- Judge 是否配置：`{configured}`")
        if judge_status.get("model_id") or judge_status.get("judge_model"):
            lines.append(f"- Judge 模型：`{_cell(judge_status.get('model_id') or judge_status.get('judge_model'))}`")
        if not configured:
            lines.append("- 注意：需要 LLM Judge 的数据集可能无法正常评测或无法产出完整分数。第一版只检查 Judge 状态，不自动配置 Judge。")
    else:
        lines.append("- 未获取到 Judge 状态；如评测包含需要 Judge 的数据集，请人工确认 EvalScope 服务已配置 Judge。")
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

    lines.append("## 5. EvalScope 原始汇总表")
    lines.append("")
    if result and result.report_table:
        lines.append("```text")
        lines.append(redact_text(result.report_table))
        lines.append("```")
    else:
        lines.append("暂无。")
    lines.append("")

    lines.append("## 6. 附录：标准化结果 JSON")
    lines.append("")
    lines.append("```json")
    lines.append(_json_block(result.model_dump(mode="json") if result else {}))
    lines.append("```")
    lines.append("")

    lines.append("## 7. 附录：脱敏后的原始结果摘要")
    lines.append("")
    lines.append("```json")
    lines.append(_json_block(task.raw_result or task.raw_status_response or task.raw_submit_response or {}))
    lines.append("```")
    lines.append("")

    path.write_text(redact_text("\n".join(lines)), encoding="utf-8")
    return path
