from fastapi.testclient import TestClient

from app.intelligence.schemas import IntelligenceProgress, IntelligenceTask
from app.main import app


class FakeRunner:
    def judge_status(self):
        return {"configured": True, "mode": "in_process", "model_config_id": "judge-model", "model_id": "judge-upstream", "source": "analysis_model", "required_datasets": []}

    async def submit_default(self, model_id: str):
        return IntelligenceTask(task_id="intel_task_20260806120000_aaaaaaaa", evalscope_task_id="intel_task_20260806120000_aaaaaaaa", model_id=model_id, evalscope_base_url="in-process", status="pending")

    async def submit_custom(self, **kwargs):
        return IntelligenceTask(task_id="intel_task_20260806120000_bbbbbbbb", evalscope_task_id="intel_task_20260806120000_bbbbbbbb", model_id=kwargs["model_id"], datasets=kwargs["datasets"], evalscope_base_url="in-process", status="pending")

    async def refresh_status(self, task_id: str):
        if task_id == "missing":
            return None
        return IntelligenceTask(
            task_id=task_id,
            evalscope_task_id=task_id,
            model_id="m1",
            evalscope_base_url="in-process",
            status="running",
            progress="能力评测进行中：gsm8k 5/10（50.0%），数据集 1/1",
            progress_detail=IntelligenceProgress(
                status="running",
                current_dataset="gsm8k",
                dataset_index=1,
                dataset_total=1,
                processed_count=5,
                total_count=10,
                percent=50.0,
                overall_percent=50.0,
                message="能力评测进行中：gsm8k 5/10（50.0%），数据集 1/1",
            ),
        )


    async def cancel(self, task_id: str):
        if task_id == "missing":
            return None
        return IntelligenceTask(task_id=task_id, evalscope_task_id=task_id, model_id="m1", evalscope_base_url="in-process", status="interrupted", progress="任务已取消")

    async def fetch_result(self, task_id: str):
        if task_id == "missing":
            return None
        return IntelligenceTask(task_id=task_id, evalscope_task_id=task_id, model_id="m1", evalscope_base_url="in-process", status="completed")


def test_intelligence_openapi_paths_present():
    paths = app.openapi()["paths"]

    assert "/api/intelligence/evalscope/health" in paths
    assert "/api/intelligence/evalscope/tasks" in paths
    assert "/api/intelligence/tasks/default" in paths
    assert "/api/intelligence/tasks/{task_id}/result" in paths
    assert "/api/intelligence/tasks/{task_id}/progress" in paths
    assert "/api/intelligence/reports/{task_id}" in paths


def test_intelligence_routes_happy_path(monkeypatch):
    from app.api import routes_intelligence

    monkeypatch.setattr(routes_intelligence, "_runner", lambda: FakeRunner())
    monkeypatch.setattr(routes_intelligence, "evalscope_health", lambda: {"status": "ok", "mode": "in_process", "evalscope_version": "test"})
    monkeypatch.setattr(routes_intelligence, "local_dataset_metadata", lambda config: {"total": 1, "datasets": {"gsm8k": {"pretty_name": "GSM8K"}}})
    client = TestClient(app)

    assert client.get("/api/intelligence/evalscope/health").json()["status"] == "ok"
    judge = client.get("/api/intelligence/evalscope/judge-config").json()
    assert judge["configured"] is True
    assert judge["source"] == "analysis_model"
    assert client.get("/api/intelligence/datasets/local").json()["total"] == 1
    submitted = client.post("/api/intelligence/tasks/default", json={"model_id": "m1"}).json()
    assert submitted["evalscope_base_url"] == "in-process"
    custom = client.post("/api/intelligence/tasks", json={"model_id": "m1", "datasets": ["gsm8k"]}).json()
    assert custom["datasets"] == ["gsm8k"]
    status = client.get("/api/intelligence/tasks/some").json()
    assert status["status"] == "running"
    assert status["progress_detail"]["processed_count"] == 5
    progress = client.get("/api/intelligence/tasks/some/progress").json()
    assert progress["progress"] == "能力评测进行中：gsm8k 5/10（50.0%），数据集 1/1"
    assert progress["progress_detail"]["overall_percent"] == 50.0
    assert client.get("/api/intelligence/tasks/some/result").json()["status"] == "completed"


def test_intelligence_routes_errors(monkeypatch):
    from app.api import routes_intelligence

    monkeypatch.setattr(routes_intelligence, "_runner", lambda: FakeRunner())
    monkeypatch.setattr(routes_intelligence, "evalscope_health", lambda: {"status": "error", "error": "boom"})
    client = TestClient(app)

    assert client.get("/api/intelligence/evalscope/health").status_code == 502
    missing = client.get("/api/intelligence/tasks/missing")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "intelligence_task_not_found"


def test_intelligence_report_route_returns_markdown(tmp_path, monkeypatch):
    from app.api import routes_intelligence

    report = tmp_path / "report.md"
    report.write_text("# report", encoding="utf-8")
    task = IntelligenceTask(task_id="intel_task_20260806120000_aaaaaaaa", model_id="m1", evalscope_base_url="in-process", report_path=str(report))

    class Store:
        def get(self, task_id):
            return task

    monkeypatch.setattr(routes_intelligence, "IntelligenceTaskStore", lambda: Store())
    client = TestClient(app)

    response = client.get(f"/api/intelligence/reports/{task.task_id}")
    assert response.status_code == 200
    assert "# report" in response.text


def test_intelligence_cancel_route(monkeypatch):
    from app.api import routes_intelligence

    monkeypatch.setattr(routes_intelligence, "_runner", lambda: FakeRunner())
    client = TestClient(app)

    response = client.post("/api/intelligence/tasks/some/cancel")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "interrupted"
    assert client.post("/api/intelligence/tasks/missing/cancel").status_code == 404
