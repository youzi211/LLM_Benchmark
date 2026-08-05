from __future__ import annotations

import json
import re
from pathlib import Path

from app.core.models import MetricResult, TaskResult
from app.core.plans import format_metric_label
from app.reports.facts import build_report_fact_pack
from app.reports.schemas import ReportAnalysis, ReportFactPack, skipped_analysis

_SECRET_RE = re.compile(r"(?<![A-Za-z0-9_-])(?:sk|ark)-[A-Za-z0-9._-]+")
_STATUS_NAMES = {
    "completed": "已完成",
    "error": "异常",
    "skipped": "已跳过",
}


def _redact_match(match: re.Match) -> str:
    prefix = match.group(0).split("-")[0]
    return f"{prefix}-***"


def redact_text(text: str) -> str:
    return _SECRET_RE.sub(_redact_match, text)


def _inline_text(value) -> str:
    return redact_text(str(value)).replace("\r\n", " ").replace("\n", " ").replace("\r", " ")


def _table_cell(value) -> str:
    return _inline_text(value).replace("|", r"\|")


def _json_block(data) -> str:
    return redact_text(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def _status_label(status: str) -> str:
    name = _STATUS_NAMES.get(status, status)
    return f"{name}（{status}）" if name != status else status


def _metric_label(item: MetricResult) -> str:
    if item.metric_name:
        return f"{item.metric_name}（{item.metric_id}）"
    return format_metric_label(item.metric_id)


def _bullet_list(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items] if items else ["- 无"]


def _analysis_section(analysis: ReportAnalysis) -> list[str]:
    lines: list[str] = []
    lines.append("## 0. LLM 分析摘要")
    lines.append("")
    lines.append(f"- 分析状态：`{_status_label(analysis.analysis_status)}`")
    if analysis.analysis_model_id:
        lines.append(f"- 分析模型 ID：`{analysis.analysis_model_id}`")
    if analysis.analysis_status == "completed":
        if analysis.one_sentence_summary:
            lines.append(f"- 一句话总结：{analysis.one_sentence_summary}")
        if analysis.overall_assessment:
            lines.append(f"- 总体评估：{analysis.overall_assessment}")
        if analysis.key_findings:
            lines.append("")
            lines.append("### 关键发现")
            lines.append("")
            lines.extend(_bullet_list(analysis.key_findings))
        if analysis.risks:
            lines.append("")
            lines.append("### 风险点")
            lines.append("")
            lines.extend(_bullet_list(analysis.risks))
        if analysis.recommended_next_steps:
            lines.append("")
            lines.append("### 建议下一步")
            lines.append("")
            lines.extend(_bullet_list(analysis.recommended_next_steps))
        if analysis.metric_notes:
            lines.append("")
            lines.append("### 指标备注")
            lines.append("")
            lines.append("| 指标 | 备注 | 严重级别 |")
            lines.append("|---|---|---|")
            for note in analysis.metric_notes:
                lines.append(
                    f"| `{_table_cell(note.metric_id)}` | {_table_cell(note.note)} | {_table_cell(note.severity)} |"
                )
    else:
        reason = analysis.error_message or analysis.one_sentence_summary or analysis.overall_assessment or "未提供具体原因。"
        lines.append(f"- 说明：{reason}")
        if analysis.raw_excerpt:
            lines.append("")
            lines.append("### 原始摘要")
            lines.append("")
            lines.append("```")
            lines.append(redact_text(str(analysis.raw_excerpt)))
            lines.append("```")
    lines.append("")
    return lines


def _task_overview_section(result: TaskResult, analysis: ReportAnalysis) -> list[str]:
    lines: list[str] = []
    lines.append("## 1. 任务概览")
    lines.append("")
    lines.append(f"- 任务 ID：`{result.task_id}`")
    lines.append(f"- 模型配置 ID：`{result.model_id}`")
    if result.model_config_name:
        lines.append(f"- 模型配置名称：`{result.model_config_name}`")
    if result.upstream_model_name:
        lines.append(f"- API 模型名称（model）：`{result.upstream_model_name}`")
    if result.protocol:
        lines.append(f"- 协议：`{result.protocol}`")
    lines.append(f"- 评测计划 ID：`{result.plan_id}`")
    lines.append(f"- 总耗时：`{result.duration_ms} ms`")
    if analysis.analysis_model_id:
        lines.append(f"- 报告分析模型 ID：`{analysis.analysis_model_id}`")
    lines.append("")
    return lines


def _dashboard_section(facts: ReportFactPack) -> list[str]:
    lines: list[str] = []
    lines.append("## 2. 指标仪表盘")
    lines.append("")
    lines.append("| 指标总数 | 已完成 | 异常 | 已跳过 |")
    lines.append("|---|---|---|---|")
    counts = facts.status_counts
    lines.append(f"| {counts.total} | {counts.completed} | {counts.error} | {counts.skipped} |")
    lines.append("")
    return lines


def _metrics_summary_section(facts: ReportFactPack) -> list[str]:
    lines: list[str] = []
    lines.append("## 3. 指标总表")
    lines.append("")
    lines.append("| 指标 | 状态 | 核心观测 | 建议关注 |")
    lines.append("|---|---|---|---|")
    for fact in facts.metric_facts:
        if fact.metric_name:
            metric_label = fact.metric_name
        else:
            metric_label = format_metric_label(fact.metric_id)
        lines.append(
            f"| {_table_cell(metric_label)} | {_table_cell(_status_label(fact.status))} | "
            f"{_table_cell(fact.core_observation)} | {_table_cell(fact.suggested_focus)} |"
        )
    lines.append("")
    return lines


def _metric_details_section(result: TaskResult) -> list[str]:
    lines: list[str] = []
    lines.append("## 4. 指标明细")
    lines.append("")
    for item in result.results:
        lines.append(f"### {_metric_label(item)}")
        lines.append("")
        lines.append(f"- 状态：`{_status_label(item.status)}`")
        lines.append(f"- 摘要：{item.summary}")
        if item.metric_id == "token_usage_accuracy":
            lines.append("")
            lines.append("本地 token 数为估算值，仅用于辅助观察，不作为自动判定依据。")
        lines.append("")
        lines.append("#### 观测数据")
        lines.append("")
        lines.append("```json")
        lines.append(_json_block(item.observations))
        lines.append("```")
        if item.errors:
            lines.append("")
            lines.append("#### 错误信息")
            lines.append("")
            lines.append("```json")
            lines.append(_json_block(item.errors))
            lines.append("```")
        lines.append("")
    return lines


def _appendix_section(facts: ReportFactPack, analysis: ReportAnalysis) -> list[str]:
    lines: list[str] = []
    lines.append("## 5. 附录")
    lines.append("")
    lines.append("### 评测事实包（JSON）")
    lines.append("")
    lines.append("```json")
    lines.append(_json_block(facts.model_dump(mode="json")))
    lines.append("```")
    lines.append("")
    lines.append("### LLM 分析报告（JSON）")
    lines.append("")
    lines.append("```json")
    lines.append(_json_block(analysis.model_dump(mode="json")))
    lines.append("```")
    lines.append("")
    return lines


def write_markdown_report(
    result: TaskResult,
    reports_dir: Path,
    facts: ReportFactPack | None = None,
    analysis: ReportAnalysis | None = None,
) -> Path:
    facts = facts or build_report_fact_pack(result)
    analysis = analysis or skipped_analysis("未执行 LLM 报告分析")
    date_part = result.started_at.strftime("%Y-%m-%d")
    path = reports_dir / date_part / f"{result.task_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append(f"# 大模型 API 评测报告 - {result.task_id}")
    lines.append("")
    lines.extend(_analysis_section(analysis))
    lines.extend(_task_overview_section(result, analysis))
    lines.extend(_dashboard_section(facts))
    lines.extend(_metrics_summary_section(facts))
    lines.extend(_metric_details_section(result))
    lines.extend(_appendix_section(facts, analysis))
    rendered = "\n".join(lines)
    path.write_text(redact_text(rendered), encoding="utf-8")
    return path


