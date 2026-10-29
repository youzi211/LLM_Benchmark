from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.core.models import MetricResult, TaskResult
from app.intelligence.schemas import IntelligenceNormalizedResult, IntelligenceTask
from app.main import app
from app.stress.schemas import StressNormalizedResult, StressTask


def test_basic_task_list_omits_large_result_payload(monkeypatch):
    from app.api import routes_tasks

    task = TaskResult(
        task_id="basic-summary",
        status="completed",
        model_id="model-a",
        plan_id="gateway_acceptance_v1",
        metric_ids=["usage"],
        started_at=datetime.now(UTC),
        results=[
            MetricResult(
                metric_id="usage",
                status="completed",
                summary="ok",
                observations={"large": "payload"},
            ),
        ],
        analysis={"large": "payload"},
    )

    class Store:
        def list(self, limit):
            return [task]

    monkeypatch.setattr(routes_tasks, "TaskStore", lambda: Store())

    response = TestClient(app).get("/api/tasks?limit=50")

    assert response.status_code == 200, response.text
    payload = response.json()[0]
    assert "results" not in payload
    assert "analysis" not in payload
    assert payload["metric_ids"] == ["usage"]


def test_stress_task_list_omits_raw_result(monkeypatch):
    from app.api import routes_stress

    task = StressTask(
        task_id="stress-summary",
        model_id="model-a",
        evalscope_base_url="in-process",
        status="completed",
        raw_result={"large": "payload"},
        normalized_result=StressNormalizedResult(task_id="stress-summary", summary={"best_req_throughput": 8}),
    )

    class Store:
        def list(self, limit):
            return [task]

    monkeypatch.setattr(routes_stress, "StressTaskStore", lambda: Store())

    response = TestClient(app).get("/api/stress/tasks?limit=50")

    assert response.status_code == 200, response.text
    payload = response.json()[0]
    assert "raw_result" not in payload
    assert payload["normalized_result"]["summary"]["best_req_throughput"] == 8


def test_stress_task_list_backfills_legacy_runs_without_raw_result(monkeypatch):
    from app.api import routes_stress

    task = StressTask(
        task_id="stress-legacy-summary",
        model_id="model-a",
        evalscope_base_url="in-process",
        status="completed",
        raw_result={
            "runs": [{
                "parallel": 2,
                "total": 10,
                "success": 10,
                "failed": 0,
                "request_throughput": 7.5,
            }],
        },
        normalized_result=StressNormalizedResult(task_id="stress-legacy-summary", runs=[]),
    )

    class Store:
        def list(self, limit):
            return [task]

    monkeypatch.setattr(routes_stress, "StressTaskStore", lambda: Store())

    response = TestClient(app).get("/api/stress/tasks?limit=50")

    assert response.status_code == 200, response.text
    payload = response.json()[0]
    assert "raw_result" not in payload
    assert payload["normalized_result"]["runs"][0]["request_throughput"] == 7.5


def test_intelligence_task_list_omits_raw_result(monkeypatch):
    from app.api import routes_intelligence

    task = IntelligenceTask(
        task_id="intel-summary",
        model_id="model-a",
        evalscope_base_url="in-process",
        status="completed",
        raw_result={"large": "payload"},
        normalized_result=IntelligenceNormalizedResult(task_id="intel-summary"),
    )

    class Store:
        def list(self, limit):
            return [task]

    monkeypatch.setattr(routes_intelligence, "IntelligenceTaskStore", lambda: Store())

    response = TestClient(app).get("/api/intelligence/tasks?limit=50")

    assert response.status_code == 200, response.text
    payload = response.json()[0]
    assert "raw_result" not in payload
    assert "normalized_result" not in payload
    assert payload["task_id"] == "intel-summary"
