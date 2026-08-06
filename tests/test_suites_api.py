from __future__ import annotations

from fastapi.testclient import TestClient

from app.api import routes_suites
from app.main import app
from app.suites.schemas import SuiteDefaultRunRequest, SuiteRun
from app.suites.store import SuiteRunStore


def test_suite_schedule_routes_are_not_swallowed_by_suite_id(temp_data_dirs, monkeypatch):
    monkeypatch.setenv("LLM_BENCHMARK_SCHEDULER_DISABLED", "1")
    client = TestClient(app)

    response = client.post(
        "/api/suites/schedules",
        json={
            "name": "nightly-demo",
            "model_id": "demo-chat",
            "time_of_day": "02:00",
            "timezone": "Asia/Shanghai",
            "stress_parallel": [1, 5],
            "stress_number": [10, 50],
        },
    )

    assert response.status_code == 200, response.text
    schedule = response.json()
    assert schedule["schedule_id"].startswith("suite_schedule_")
    assert schedule["request"]["wait_for_completion"] is True
    assert schedule["request"]["stress_options"]["parallel"] == [1, 5]

    listed = client.get("/api/suites/schedules")
    assert listed.status_code == 200
    assert listed.json()[0]["schedule_id"] == schedule["schedule_id"]

    fetched = client.get(f"/api/suites/schedules/{schedule['schedule_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["schedule_id"] == schedule["schedule_id"]

    deleted = client.delete(f"/api/suites/schedules/{schedule['schedule_id']}")
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True, "schedule_id": schedule["schedule_id"]}


def test_suite_default_and_report_routes(temp_data_dirs, monkeypatch):
    data_dir, reports_dir = temp_data_dirs
    monkeypatch.setenv("LLM_BENCHMARK_SCHEDULER_DISABLED", "1")
    report_path = reports_dir / "overview" / "2026-08-06" / "suite-overview.md"
    report_path.parent.mkdir(parents=True)
    report_path.write_text("# 模型评测总览报告\n", encoding="utf-8")

    class FakeRunner:
        async def start_default(self, request: SuiteDefaultRunRequest, schedule_id: str | None = None):
            suite = SuiteRun(
                suite_id="suite_route_demo",
                model_id=request.model_id,
                title=request.title,
                status="completed",
                request=request,
                schedule_id=schedule_id,
                overview_id="overview_route_demo",
                overview_report_path=str(report_path),
            )
            SuiteRunStore(data_dir / "suite_runs").save(suite)
            return suite

    monkeypatch.setattr(routes_suites, "_runner", lambda: FakeRunner())
    client = TestClient(app)

    created = client.post(
        "/api/suites/default",
        json={"model_id": "demo-chat", "wait_for_completion": True},
    )

    assert created.status_code == 200, created.text
    assert created.json()["suite_id"] == "suite_route_demo"

    fetched = client.get("/api/suites/suite_route_demo")
    assert fetched.status_code == 200
    assert fetched.json()["overview_id"] == "overview_route_demo"

    markdown = client.get("/api/suites/suite_route_demo/report")
    assert markdown.status_code == 200
    assert "模型评测总览报告" in markdown.text
