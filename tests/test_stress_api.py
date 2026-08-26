from fastapi.testclient import TestClient

from app.main import app
from app.stress.schemas import StressTask


class FakeRunner:
    async def submit_default(self, model_id: str, options=None):
        return StressTask(
            task_id="stress_task_20260806120000_aaaaaaaa",
            evalscope_stress_task_id="stress_task_20260806120000_aaaaaaaa",
            model_id=model_id,
            protocol="chat_completions",
            evalscope_base_url="in-process",
            status="pending",
        )

    async def refresh_status(self, task_id: str):
        if task_id == "missing":
            return None
        return StressTask(task_id=task_id, model_id="m1", protocol="chat_completions", evalscope_base_url="in-process", status="running")


    async def cancel(self, task_id: str):
        if task_id == "missing":
            return None
        return StressTask(task_id=task_id, model_id="m1", protocol="chat_completions", evalscope_base_url="in-process", status="interrupted", progress="任务已取消")

    async def fetch_result(self, task_id: str):
        if task_id == "missing":
            return None
        return StressTask(task_id=task_id, model_id="m1", protocol="chat_completions", evalscope_base_url="in-process", status="completed")


def test_stress_openapi_paths_present():
    paths = app.openapi()["paths"]

    assert "/api/stress/evalscope/health" in paths
    assert "/api/stress/tasks/default" in paths
    assert "/api/stress/tasks/{task_id}/result" in paths
    assert "/api/stress/reports/{task_id}" in paths


def test_stress_routes_happy_path(monkeypatch):
    from app.api import routes_stress

    monkeypatch.setattr(routes_stress, "_runner", lambda: FakeRunner())
    monkeypatch.setattr(routes_stress, "evalscope_health", lambda: {"status": "ok", "mode": "in_process", "evalscope_version": "test"})
    client = TestClient(app)

    assert client.get("/api/stress/evalscope/health").json()["mode"] == "in_process"
    submitted = client.post("/api/stress/tasks/default", json={"model_id": "m1", "parallel": [1], "number": [1]}).json()
    assert submitted["evalscope_base_url"] == "in-process"
    assert client.get("/api/stress/tasks/some").json()["status"] == "running"
    assert client.get("/api/stress/tasks/some/result").json()["status"] == "completed"


def test_stress_routes_errors(monkeypatch):
    from app.api import routes_stress

    monkeypatch.setattr(routes_stress, "_runner", lambda: FakeRunner())
    monkeypatch.setattr(routes_stress, "evalscope_health", lambda: {"status": "error", "error": "boom"})
    client = TestClient(app)

    assert client.get("/api/stress/evalscope/health").status_code == 502
    missing = client.get("/api/stress/tasks/missing")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "stress_task_not_found"


def test_stress_report_route_returns_markdown(tmp_path, monkeypatch):
    from app.api import routes_stress

    report = tmp_path / "report.md"
    report.write_text("# report", encoding="utf-8")
    task = StressTask(task_id="stress_task_20260806120000_aaaaaaaa", model_id="m1", protocol="chat_completions", evalscope_base_url="in-process", report_path=str(report))

    class Store:
        def get(self, task_id):
            return task

    monkeypatch.setattr(routes_stress, "StressTaskStore", lambda: Store())
    client = TestClient(app)

    response = client.get(f"/api/stress/reports/{task.task_id}")
    assert response.status_code == 200
    assert "# report" in response.text


def test_stress_cancel_route(monkeypatch):
    from app.api import routes_stress

    monkeypatch.setattr(routes_stress, "_runner", lambda: FakeRunner())
    client = TestClient(app)

    response = client.post("/api/stress/tasks/some/cancel")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "interrupted"
    assert client.post("/api/stress/tasks/missing/cancel").status_code == 404
