from pathlib import Path

from fastapi.testclient import TestClient

from app.intelligence.evalscope_client import EvalScopeClientError
from app.intelligence.schemas import IntelligenceTask
from app.main import app


class FakeClient:
    async def health(self):
        return {"status": "ok"}

    async def judge_config(self):
        return {"configured": True}

    async def tasks(self):
        return [{"task_id": "eval-1"}]

    async def datasets(self):
        return {"total": 1, "datasets": {"gsm8k": {"pretty_name": "GSM8K"}}}

    async def local_datasets(self):
        return {"total": 1, "datasets": {"gsm8k": {"pretty_name": "GSM8K"}}}


class FakeRunner:
    async def submit_default(self, model_id: str):
        return IntelligenceTask(task_id="intel_task_20260806120000_aaaaaaaa", evalscope_task_id="eval-1", model_id=model_id, evalscope_base_url="http://evalscope", status="pending")

    async def submit_custom(self, **kwargs):
        return IntelligenceTask(task_id="intel_task_20260806120000_bbbbbbbb", evalscope_task_id="eval-2", model_id=kwargs["model_id"], datasets=kwargs["datasets"], evalscope_base_url="http://evalscope", status="pending")

    async def refresh_status(self, task_id: str):
        if task_id == "missing":
            return None
        return IntelligenceTask(task_id=task_id, evalscope_task_id="eval-1", model_id="m1", evalscope_base_url="http://evalscope", status="running")

    async def fetch_result(self, task_id: str):
        if task_id == "missing":
            return None
        return IntelligenceTask(task_id=task_id, evalscope_task_id="eval-1", model_id="m1", evalscope_base_url="http://evalscope", status="completed")


def test_intelligence_openapi_paths_present():
    paths = app.openapi()["paths"]

    assert "/api/intelligence/evalscope/health" in paths
    assert "/api/intelligence/evalscope/tasks" in paths
    assert "/api/intelligence/tasks/default" in paths
    assert "/api/intelligence/tasks/{task_id}/result" in paths
    assert "/api/intelligence/reports/{task_id}" in paths


def test_intelligence_routes_happy_path(monkeypatch):
    from app.api import routes_intelligence

    monkeypatch.setattr(routes_intelligence, "_client", lambda: FakeClient())
    monkeypatch.setattr(routes_intelligence, "_runner", lambda: FakeRunner())
    client = TestClient(app)

    assert client.get("/api/intelligence/evalscope/health").json()["status"] == "ok"
    assert client.get("/api/intelligence/datasets/local").json()["total"] == 1
    submitted = client.post("/api/intelligence/tasks/default", json={"model_id": "m1"}).json()
    assert submitted["evalscope_task_id"] == "eval-1"
    custom = client.post("/api/intelligence/tasks", json={"model_id": "m1", "datasets": ["gsm8k"]}).json()
    assert custom["datasets"] == ["gsm8k"]
    assert client.get("/api/intelligence/tasks/some").json()["status"] == "running"
    assert client.get("/api/intelligence/tasks/some/result").json()["status"] == "completed"


def test_intelligence_routes_errors(monkeypatch):
    from app.api import routes_intelligence

    class ErrorClient(FakeClient):
        async def health(self):
            raise EvalScopeClientError("boom", status_code=500)

    monkeypatch.setattr(routes_intelligence, "_client", lambda: ErrorClient())
    monkeypatch.setattr(routes_intelligence, "_runner", lambda: FakeRunner())
    client = TestClient(app)

    assert client.get("/api/intelligence/evalscope/health").status_code == 502
    missing = client.get("/api/intelligence/tasks/missing")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "intelligence_task_not_found"


def test_intelligence_report_route_returns_markdown(tmp_path, monkeypatch):
    from app.api import routes_intelligence

    report = tmp_path / "report.md"
    report.write_text("# report", encoding="utf-8")
    task = IntelligenceTask(task_id="intel_task_20260806120000_aaaaaaaa", model_id="m1", evalscope_base_url="http://evalscope", report_path=str(report))

    class Store:
        def get(self, task_id):
            return task

    monkeypatch.setattr(routes_intelligence, "IntelligenceTaskStore", lambda: Store())
    client = TestClient(app)

    response = client.get(f"/api/intelligence/reports/{task.task_id}")
    assert response.status_code == 200
    assert "# report" in response.text
