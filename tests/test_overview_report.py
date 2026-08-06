from pathlib import Path

from fastapi.testclient import TestClient

from app.core.models import MetricResult, TaskResult, utc_now
from app.intelligence.schemas import (
    IntelligenceCategorySummary,
    IntelligenceDatasetResult,
    IntelligenceNormalizedResult,
    IntelligenceTask,
)
from app.main import app
from app.overview.report import build_overview_report, write_overview_markdown
from app.overview.schemas import OverviewReportRequest
from app.storage.intelligence_task_store import IntelligenceTaskStore
from app.storage.overview_report_store import OverviewReportStore
from app.storage.stress_task_store import StressTaskStore
from app.storage.task_store import TaskStore
from app.stress.schemas import StressNormalizedResult, StressRunResult, StressTask


def _seed_related_tasks(data_dir: Path, reports_dir: Path):
    started = utc_now()
    gateway_report = reports_dir / "2026-08-06" / "task_gateway.md"
    gateway_report.parent.mkdir(parents=True, exist_ok=True)
    gateway_report.write_text("# 网关报告", encoding="utf-8")
    gateway_task = TaskResult(
        task_id="task_gateway",
        status="completed",
        model_id="demo-chat",
        model_config_name="Demo Chat",
        upstream_model_name="upstream-model",
        protocol="chat_completions",
        plan_id="gateway_acceptance_v1",
        metric_ids=["connectivity", "stream_spec"],
        started_at=started,
        finished_at=started,
        duration_ms=12.0,
        results=[
            MetricResult(metric_id="connectivity", metric_name="连通性", status="completed", summary="接口可访问"),
            MetricResult(metric_id="stream_spec", metric_name="流式规范性", status="completed", summary="SSE 正常"),
        ],
        report_path=str(gateway_report),
    )
    TaskStore(data_dir / "tasks").save(gateway_task)

    intel_report = reports_dir / "intelligence" / "2026-08-06" / "intel_task_demo.md"
    intel_report.parent.mkdir(parents=True, exist_ok=True)
    intel_report.write_text("# 能力报告", encoding="utf-8")
    intel_task = IntelligenceTask(
        task_id="intel_task_demo",
        evalscope_task_id="evalscope-intel-1",
        model_id="demo-chat",
        model_config_name="Demo Chat",
        upstream_model_name="upstream-model",
        evalscope_base_url="http://evalscope/api/v1",
        status="completed",
        completed_at=started,
        report_path=str(intel_report),
        normalized_result=IntelligenceNormalizedResult(
            task_id="intel_task_demo",
            evalscope_task_id="evalscope-intel-1",
            model="upstream-model",
            status="completed",
            dataset_results=[
                IntelligenceDatasetResult(dataset="gsm8k", pretty_name="GSM8K", categories=["math"], score=70.0),
                IntelligenceDatasetResult(dataset="humaneval", pretty_name="HumanEval", categories=["code"], score=80.0),
            ],
            category_summaries=[
                IntelligenceCategorySummary(category="code", dataset_count=1, scored_dataset_count=1, average_score=80.0),
                IntelligenceCategorySummary(category="math", dataset_count=1, scored_dataset_count=1, average_score=70.0),
            ],
        ),
    )
    IntelligenceTaskStore(data_dir / "intelligence_tasks").save(intel_task)

    stress_report = reports_dir / "stress" / "2026-08-06" / "stress_task_demo.md"
    stress_report.parent.mkdir(parents=True, exist_ok=True)
    stress_report.write_text("# 压测报告", encoding="utf-8")
    stress_task = StressTask(
        task_id="stress_task_demo",
        evalscope_stress_task_id="evalscope-stress-1",
        model_id="demo-chat",
        model_config_name="Demo Chat",
        upstream_model_name="upstream-model",
        protocol="chat_completions",
        evalscope_base_url="http://evalscope/api/v1",
        status="completed",
        completed_at=started,
        report_path=str(stress_report),
        normalized_result=StressNormalizedResult(
            task_id="stress_task_demo",
            evalscope_stress_task_id="evalscope-stress-1",
            model="upstream-model",
            status="completed",
            summary={"max_success_parallel": 5, "best_req_throughput": 8.7, "first_error_parallel": 10},
            runs=[
                StressRunResult(parallel=1, total=10, success=10, failed=0, success_rate=1.0, request_throughput=2.1),
                StressRunResult(parallel=5, total=50, success=50, failed=0, success_rate=1.0, request_throughput=8.7),
            ],
        ),
    )
    StressTaskStore(data_dir / "stress_tasks").save(stress_task)
    return gateway_task, intel_task, stress_task


def test_overview_report_combines_gateway_intelligence_and_stress(temp_data_dirs):
    data_dir, reports_dir = temp_data_dirs
    _seed_related_tasks(data_dir, reports_dir)

    report = build_overview_report(
        OverviewReportRequest(
            gateway_task_id="task_gateway",
            intelligence_task_id="intel_task_demo",
            stress_task_id="stress_task_demo",
        ),
        task_store=TaskStore(data_dir / "tasks"),
        intelligence_store=IntelligenceTaskStore(data_dir / "intelligence_tasks"),
        stress_store=StressTaskStore(data_dir / "stress_tasks"),
    )
    path = write_overview_markdown(report, reports_dir)
    text = path.read_text(encoding="utf-8")

    assert report.model_id == "demo-chat"
    assert "# 模型评测总览报告 - demo-chat" in text
    assert "## 0. 一眼看懂" in text
    assert "网关接入验收" in text
    assert "EvalScope 能力评测" in text
    assert "EvalScope 压测" in text
    assert "接入验收完成：共 2 项，异常 0 项" in text
    assert "平均 Score 75.00" in text
    assert "最大无失败并发：5" in text
    assert "/api/reports/task_gateway" in text
    assert "/api/intelligence/reports/intel_task_demo" in text
    assert "/api/stress/reports/stress_task_demo" in text


def test_overview_report_api_create_get_and_download(temp_data_dirs):
    data_dir, reports_dir = temp_data_dirs
    _seed_related_tasks(data_dir, reports_dir)

    response = TestClient(app).post(
        "/api/overview/reports",
        json={
            "gateway_task_id": "task_gateway",
            "intelligence_task_id": "intel_task_demo",
            "stress_task_id": "stress_task_demo",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    overview_id = body["overview_id"]
    assert overview_id.startswith("overview_report_")
    assert body["model_id"] == "demo-chat"
    assert body["report_path"]
    assert Path(body["report_path"]).exists()
    assert OverviewReportStore(data_dir / "overview_reports").get(overview_id) is not None

    metadata = TestClient(app).get(f"/api/overview/reports/{overview_id}")
    assert metadata.status_code == 200
    assert metadata.json()["overview_id"] == overview_id

    markdown = TestClient(app).get(f"/api/overview/reports/{overview_id}/markdown")
    assert markdown.status_code == 200
    assert "模型评测总览报告" in markdown.text
    assert "详细报告入口" in markdown.text
