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

def test_suite_quick_route_uses_inline_model_without_persisting_key(temp_data_dirs, monkeypatch):
    data_dir, _ = temp_data_dirs
    monkeypatch.setenv("LLM_BENCHMARK_SCHEDULER_DISABLED", "1")
    captured = {}

    class FakeQuickRunner:
        async def start_default(self, request: SuiteDefaultRunRequest, schedule_id: str | None = None):
            captured["suite_request"] = request
            suite = SuiteRun(
                suite_id="suite_quick_demo",
                model_id=request.model_id,
                title=request.title,
                status="queued",
                request=request,
                schedule_id=schedule_id,
            )
            SuiteRunStore(data_dir / "suite_runs").save(suite)
            return suite

        async def execute(self, suite_id: str):
            captured["executed"] = suite_id

    def fake_quick_runner(request):
        captured["quick_request"] = request
        suite_request = SuiteDefaultRunRequest(
            model_id="inline_test_model",
            title=request.title or f"{request.model} 一键评测",
            run_gateway=request.run_gateway,
            run_intelligence=request.run_intelligence,
            run_stress=request.run_stress,
            gateway_metric_ids=request.gateway_metric_ids,
            wait_for_completion=request.wait_for_completion,
        )
        return FakeQuickRunner(), suite_request

    monkeypatch.setattr(routes_suites, "_quick_runner", fake_quick_runner)
    client = TestClient(app)

    response = client.post(
        "/api/suites/quick",
        json={
            "url": "http://127.0.0.1:9001/v1",
            "key": "dummy-key-should-not-be-persisted",
            "model": "demo-model",
            "run_intelligence": False,
            "run_stress": False,
            "gateway_metric_ids": ["connectivity"],
        },
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["suite_id"] == "suite_quick_demo"
    assert data["model_id"] == "inline_test_model"
    assert data["request"]["model_id"] == "inline_test_model"
    assert "dummy-key-should-not-be-persisted" not in response.text
    assert captured["quick_request"].key == "dummy-key-should-not-be-persisted"
    assert captured["suite_request"].gateway_metric_ids == ["connectivity"]
    assert not (data_dir / "models.json").exists()
    suite_file = data_dir / "suite_runs" / "suite_quick_demo.json"
    assert suite_file.exists()
    assert "dummy-key-should-not-be-persisted" not in suite_file.read_text(encoding="utf-8")


def test_suite_quick_request_builds_transient_model_from_url_key_model(temp_data_dirs):
    from app.suites.schemas import SuiteQuickRunRequest

    request = SuiteQuickRunRequest(
        base_url="http://gateway.example/v1/chat/completions",
        api_key="<test-key>",
        model="demo-model",
        run_stress=False,
    )

    model_config = request.to_inline_model_config()
    suite_request = request.to_suite_request(model_config.id)

    assert model_config.id.startswith("inline_")
    assert model_config.base_url == "http://gateway.example/v1"
    assert model_config.api_key == "<test-key>"
    assert model_config.model == "demo-model"
    assert suite_request.model_id == model_config.id
    assert suite_request.title == "demo-model 一键评测"
    assert suite_request.run_stress is False
