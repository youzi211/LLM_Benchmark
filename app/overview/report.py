from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.core.models import MetricResult, TaskResult
from app.intelligence.schemas import IntelligenceTask
from app.overview.schemas import OverviewComponent, OverviewReport, OverviewReportRequest
from app.reports.markdown import redact_text
from app.storage.intelligence_task_store import IntelligenceTaskStore
from app.storage.stress_task_store import StressTaskStore
from app.storage.task_store import TaskStore
from app.stress.schemas import StressTask


def _cell(value: Any) -> str:
    return redact_text(str(value if value is not None else "-")).replace("|", r"\|").replace("\r\n", " ").replace("\n", " ").replace("\r", " ")


def _fmt(value: Any, digits: int = 2, suffix: str = "") -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.{digits}f}{suffix}"
    return f"{value}{suffix}"


def _metric_status_counts(results: list[MetricResult]) -> dict[str, int]:
    counts = {"total": len(results), "completed": 0, "error": 0, "skipped": 0}
    for item in results:
        if item.status in counts:
            counts[item.status] += 1
    return counts


def _gateway_component(task: TaskResult | None, requested_id: str | None) -> OverviewComponent:
    if task is None:
        return OverviewComponent(
            kind="gateway_acceptance",
            title="网关接入验收",
            task_id=requested_id,
            status="missing" if requested_id else "not_provided",
            summary="未提供网关接入验收任务。" if not requested_id else "未找到网关接入验收任务。",
            warnings=["缺少网关接入验收结果，无法判断该模型通道的协议接入健康度。"] if not requested_id else ["指定的网关接入验收任务不存在。"],
        )

    counts = _metric_status_counts(task.results)
    status = "completed" if task.status == "completed" and counts["error"] == 0 else task.status
    if task.status == "completed":
        summary = f"接入验收完成：共 {counts['total']} 项，异常 {counts['error']} 项，跳过 {counts['skipped']} 项。"
    else:
        summary = f"接入验收任务状态为 {task.status}。"
    highlights = [
        f"计划：{task.plan_id}",
        f"指标：完成 {counts['completed']} / 异常 {counts['error']} / 跳过 {counts['skipped']}",
    ]
    if task.protocol:
        highlights.append(f"协议：{task.protocol}")
    warnings = [item.summary for item in task.results if item.status == "error"]
    return OverviewComponent(
        kind="gateway_acceptance",
        title="网关接入验收",
        task_id=task.task_id,
        status=status,
        summary=summary,
        report_path=task.report_path,
        report_endpoint=f"/api/reports/{task.task_id}",
        highlights=highlights,
        metrics=counts,
        warnings=warnings,
    )


def _average_score(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _intelligence_component(task: IntelligenceTask | None, requested_id: str | None) -> OverviewComponent:
    if task is None:
        return OverviewComponent(
            kind="intelligence",
            title="EvalScope 能力评测",
            task_id=requested_id,
            status="missing" if requested_id else "not_provided",
            summary="未提供 EvalScope 能力评测任务。" if not requested_id else "未找到 EvalScope 能力评测任务。",
            warnings=["缺少能力评测结果，无法展示代码、数学、知识、推理等能力维度表现。"] if not requested_id else ["指定的能力评测任务不存在。"],
        )

    result = task.normalized_result
    dataset_count = len(result.dataset_results) if result else 0
    scored = [item.score for item in result.dataset_results if item.score is not None] if result else []
    avg_score = _average_score(scored)
    categories = result.category_summaries if result else []
    summary = "能力评测尚未形成标准化结果。"
    if result:
        summary = f"能力评测{task.status}：数据集 {dataset_count} 个，有分数 {len(scored)} 个，平均 Score {_fmt(avg_score)}。"
    highlights = []
    if categories:
        top_categories = sorted(
            [item for item in categories if item.average_score is not None],
            key=lambda item: item.average_score or 0,
            reverse=True,
        )[:3]
        highlights.extend([f"{item.category}: {_fmt(item.average_score)}" for item in top_categories])
    warnings = []
    if task.status == "failed" and task.error:
        warnings.append(str(task.error.get("message") or task.error))
    if task.message:
        warnings.append(task.message)
    return OverviewComponent(
        kind="intelligence",
        title="EvalScope 能力评测",
        task_id=task.task_id,
        status=task.status,
        summary=summary,
        report_path=task.report_path,
        report_endpoint=f"/api/intelligence/reports/{task.task_id}",
        highlights=highlights,
        metrics={"dataset_count": dataset_count, "scored_dataset_count": len(scored), "average_score": avg_score},
        warnings=warnings,
    )


def _stress_component(task: StressTask | None, requested_id: str | None) -> OverviewComponent:
    if task is None:
        return OverviewComponent(
            kind="stress",
            title="EvalScope 压测",
            task_id=requested_id,
            status="missing" if requested_id else "not_provided",
            summary="未提供 EvalScope 压测任务。" if not requested_id else "未找到 EvalScope 压测任务。",
            warnings=["缺少正式压测结果，无法展示并发、吞吐、延迟分位数和容量边界。"] if not requested_id else ["指定的压测任务不存在。"],
        )

    result = task.normalized_result
    summary_data = result.summary if result else {}
    runs = result.runs if result else []
    best_rps = summary_data.get("best_req_throughput")
    max_success = summary_data.get("max_success_parallel")
    first_error = summary_data.get("first_error_parallel")
    summary = "压测尚未形成标准化结果。"
    if result:
        summary = f"压测{task.status}：并发档位 {len(runs)} 个，最大无失败并发 {_fmt(max_success)}，最高 RPS {_fmt(best_rps)}。"
    warnings = []
    if first_error is not None:
        warnings.append(f"首次出现失败/限流的并发档位：{first_error}")
    if result and result.errors:
        warnings.append(f"标准化异常记录数：{len(result.errors)}")
    if task.status == "failed" and task.error:
        warnings.append(str(task.error.get("message") or task.error))
    return OverviewComponent(
        kind="stress",
        title="EvalScope 压测",
        task_id=task.task_id,
        status=task.status,
        summary=summary,
        report_path=task.report_path,
        report_endpoint=f"/api/stress/reports/{task.task_id}",
        highlights=[
            f"最大无失败并发：{_fmt(max_success)}",
            f"最高 RPS：{_fmt(best_rps)}",
            f"首次失败/限流并发：{_fmt(first_error)}",
        ],
        metrics={"run_count": len(runs), "max_success_parallel": max_success, "best_req_throughput": best_rps, "first_error_parallel": first_error},
        warnings=warnings,
    )


def build_overview_report(
    request: OverviewReportRequest,
    task_store: TaskStore | None = None,
    intelligence_store: IntelligenceTaskStore | None = None,
    stress_store: StressTaskStore | None = None,
) -> OverviewReport:
    task_store = task_store or TaskStore()
    intelligence_store = intelligence_store or IntelligenceTaskStore()
    stress_store = stress_store or StressTaskStore()

    gateway_task = task_store.get(request.gateway_task_id) if request.gateway_task_id else None
    intelligence_task = intelligence_store.get(request.intelligence_task_id) if request.intelligence_task_id else None
    stress_task = stress_store.get(request.stress_task_id) if request.stress_task_id else None

    model_id = request.model_id or (gateway_task.model_id if gateway_task else None) or (intelligence_task.model_id if intelligence_task else None) or (stress_task.model_id if stress_task else None)
    components = [
        _gateway_component(gateway_task, request.gateway_task_id),
        _stress_component(stress_task, request.stress_task_id),
        _intelligence_component(intelligence_task, request.intelligence_task_id),
    ]
    provided_components = [item for item in components if item.status not in {"not_provided"}]
    completed = sum(1 for item in provided_components if item.status == "completed")
    warning_count = sum(len(item.warnings) for item in components)

    return OverviewReport(
        title=request.title or "模型评测总览报告",
        model_id=model_id,
        gateway_task_id=request.gateway_task_id,
        intelligence_task_id=request.intelligence_task_id,
        stress_task_id=request.stress_task_id,
        components=components,
        summary={
            "provided_component_count": len(provided_components),
            "completed_component_count": completed,
            "warning_count": warning_count,
        },
    )


def write_overview_markdown(report: OverviewReport, reports_dir: Path | None = None) -> Path:
    reports_dir = reports_dir or Path(os.getenv("LLM_BENCHMARK_REPORTS_DIR", "reports"))
    date_part = report.created_at.strftime("%Y-%m-%d")
    path = reports_dir / "overview" / date_part / f"{report.overview_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    lines.append(f"# {report.title} - {report.model_id or report.overview_id}")
    lines.append("")
    lines.append("## 0. 一眼看懂")
    lines.append("")
    lines.append("| 模块 | 状态 | 摘要 | 详情入口 |")
    lines.append("|---|---|---|---|")
    for component in report.components:
        endpoint = component.report_endpoint or "-"
        lines.append(f"| {_cell(component.title)} | `{_cell(component.status)}` | {_cell(component.summary)} | `{_cell(endpoint)}` |")
    lines.append("")
    lines.append("> 本报告只做中文总览、导航和归档；EvalScope 能力评测与压测的详细表格、可视化和原始输出仍以 EvalScope 侧结果为准。")
    lines.append("")

    lines.append("## 1. 模型与任务信息")
    lines.append("")
    lines.append(f"- 总览报告 ID：`{report.overview_id}`")
    lines.append(f"- 模型配置 ID：`{report.model_id or '-'}`")
    lines.append(f"- 创建时间：`{report.created_at}`")
    lines.append(f"- 网关接入验收任务：`{report.gateway_task_id or '-'}`")
    lines.append(f"- EvalScope 能力评测任务：`{report.intelligence_task_id or '-'}`")
    lines.append(f"- EvalScope 压测任务：`{report.stress_task_id or '-'}`")
    lines.append("")

    lines.append("## 2. 网关接入验收摘要")
    lines.append("")
    _append_component_detail(lines, report.components[0])

    lines.append("## 3. EvalScope 压测摘要")
    lines.append("")
    _append_component_detail(lines, report.components[1])

    lines.append("## 4. EvalScope 能力评测摘要")
    lines.append("")
    _append_component_detail(lines, report.components[2])

    lines.append("## 5. 详细报告入口")
    lines.append("")
    lines.append("| 报告 | API 入口 | 本地路径 |")
    lines.append("|---|---|---|")
    for component in report.components:
        lines.append(f"| {_cell(component.title)} | `{_cell(component.report_endpoint or '-')}` | `{_cell(component.report_path or '-')}` |")
    lines.append("")

    path.write_text(redact_text("\n".join(lines)), encoding="utf-8")
    report.report_path = str(path)
    return path


def _append_component_detail(lines: list[str], component: OverviewComponent) -> None:
    lines.append(f"- 状态：`{_cell(component.status)}`")
    if component.task_id:
        lines.append(f"- 任务 ID：`{_cell(component.task_id)}`")
    lines.append(f"- 摘要：{_cell(component.summary)}")
    if component.highlights:
        lines.append("- 关键观测：")
        for item in component.highlights:
            lines.append(f"  - {_cell(item)}")
    if component.warnings:
        lines.append("- 需要关注：")
        for item in component.warnings[:10]:
            lines.append(f"  - {_cell(item)}")
    if component.report_endpoint:
        lines.append(f"- 详情入口：`{_cell(component.report_endpoint)}`")
    lines.append("")
