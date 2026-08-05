from __future__ import annotations

import json
import re
from pathlib import Path

from app.core.models import MetricResult, TaskResult
from app.core.plans import format_metric_label

_SECRET_RE = re.compile(r"sk-[A-Za-z0-9._-]+")
_STATUS_NAMES = {
    "completed": "已完成",
    "error": "异常",
    "skipped": "已跳过",
}


def redact_text(text: str) -> str:
    return _SECRET_RE.sub("sk-***", text)


def _json_block(data) -> str:
    return redact_text(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def _status_label(status: str) -> str:
    name = _STATUS_NAMES.get(status, status)
    return f"{name}（{status}）" if name != status else status


def _metric_label(item: MetricResult) -> str:
    if item.metric_name:
        return f"{item.metric_name}（{item.metric_id}）"
    return format_metric_label(item.metric_id)


def write_markdown_report(result: TaskResult, reports_dir: Path) -> Path:
    date_part = result.started_at.strftime("%Y-%m-%d")
    path = reports_dir / date_part / f"{result.task_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append(f"# 大模型 API 评测报告 - {result.task_id}")
    lines.append("")
    lines.append("## 任务信息")
    lines.append("")
    lines.append(f"- 任务 ID：`{result.task_id}`")
    lines.append(f"- 任务状态：`{_status_label(result.status)}`")
    lines.append(f"- 模型配置 ID：`{result.model_id}`")
    if result.model_config_name:
        lines.append(f"- 模型配置名称：`{result.model_config_name}`")
    if result.upstream_model_name:
        lines.append(f"- API 模型名称（model）：`{result.upstream_model_name}`")
    if result.protocol:
        lines.append(f"- 协议：`{result.protocol}`")
    lines.append(f"- 评测计划 ID：`{result.plan_id}`")
    lines.append(f"- 开始时间：`{result.started_at}`")
    lines.append(f"- 结束时间：`{result.finished_at}`")
    lines.append(f"- 总耗时：`{result.duration_ms} ms`")
    lines.append("")
    lines.append("## 指标汇总")
    lines.append("")
    lines.append("| 指标 | 状态 | 摘要 |")
    lines.append("|---|---|---|")
    for item in result.results:
        lines.append(f"| {_metric_label(item)} | {_status_label(item.status)} | {item.summary} |")
    lines.append("")
    for item in result.results:
        lines.append(f"## {_metric_label(item)}")
        lines.append("")
        lines.append(f"- 状态：`{_status_label(item.status)}`")
        lines.append(f"- 摘要：{item.summary}")
        if item.metric_id == "token_usage_accuracy":
            lines.append("")
            lines.append("本地 token 数为估算值，仅用于辅助观察，不作为自动判定依据。")
        lines.append("")
        lines.append("### 观测数据")
        lines.append("")
        lines.append("```json")
        lines.append(_json_block(item.observations))
        lines.append("```")
        if item.errors:
            lines.append("")
            lines.append("### 错误信息")
            lines.append("")
            lines.append("```json")
            lines.append(_json_block(item.errors))
            lines.append("```")
        lines.append("")
    path.write_text(redact_text("\n".join(lines)), encoding="utf-8")
    return path
