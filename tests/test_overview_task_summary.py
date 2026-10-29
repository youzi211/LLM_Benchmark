from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.core.models import TaskResult
from app.intelligence.schemas import IntelligenceTask
from app.main import app
from app.stress.schemas import StressTask


def test_overview_task_summary_counts_all_tasks_before_list_truncation(monkeypatch):
    from app.api import routes_overview

    now = datetime(2026, 10, 29, 9, 0, tzinfo=UTC)
    basic = [
        TaskResult(
            task_id=f"task-{index}",
            status="completed",
            model_id="model-a",
            plan_id="gateway_acceptance_v1",
            metric_ids=["usage"],
            started_at=now,
            duration_ms=1500,
        )
        for index in range(51)
    ]
    stress = [
        StressTask(
            task_id="stress-failed",
            model_id="model-a",
            evalscope_base_url="in-process",
            status="failed",
            created_at=now,
            duration_ms=1500,
        ),
    ]
    intelligence = [
        IntelligenceTask(
            task_id="intel-running",
            model_id="model-a",
            evalscope_base_url="in-process",
            status="running",
            created_at=now,
        ),
    ]

    class Store:
        def __init__(self, tasks):
            self.tasks = tasks

        def iter_tasks(self):
            yield from self.tasks

    monkeypatch.setattr(routes_overview, "TaskStore", lambda: Store(basic))
    monkeypatch.setattr(routes_overview, "StressTaskStore", lambda: Store(stress))
    monkeypatch.setattr(routes_overview, "IntelligenceTaskStore", lambda: Store(intelligence))

    response = TestClient(app).get("/api/overview/task-summary")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["today_count"] == 53
    assert payload["final_count"] == 52
    assert payload["completed_count"] == 51
    assert payload["completion_rate"] == 98.1
    assert payload["avg_duration_ms"] == 1500


def test_overview_task_summary_uses_shanghai_date_boundary(monkeypatch):
    from app.api import routes_overview

    class Store:
        def __init__(self, tasks):
            self.tasks = tasks

        def iter_tasks(self):
            yield from self.tasks

    tasks = [
        TaskResult(
            task_id="before-midnight",
            status="completed",
            model_id="model-a",
            plan_id="gateway_acceptance_v1",
            metric_ids=["usage"],
            started_at=datetime(2026, 10, 28, 15, 59, tzinfo=UTC),
        ),
        TaskResult(
            task_id="after-midnight",
            status="completed",
            model_id="model-a",
            plan_id="gateway_acceptance_v1",
            metric_ids=["usage"],
            started_at=datetime(2026, 10, 28, 16, 1, tzinfo=UTC),
        ),
    ]
    monkeypatch.setattr(routes_overview, "TaskStore", lambda: Store(tasks))
    monkeypatch.setattr(routes_overview, "StressTaskStore", lambda: Store([]))
    monkeypatch.setattr(routes_overview, "IntelligenceTaskStore", lambda: Store([]))

    response = TestClient(app).get("/api/overview/task-summary?unused=ignored")

    assert response.status_code == 200, response.text
    assert response.json()["today_count"] == 1


def test_overview_task_summary_has_openapi_response_model():
    operation = app.openapi()["paths"]["/api/overview/task-summary"]["get"]
    schema = operation["responses"]["200"]["content"]["application/json"]["schema"]

    assert schema["$ref"].endswith("/TaskOverviewSummary")
