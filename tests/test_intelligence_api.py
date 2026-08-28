import json

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


def test_intelligence_custom_route_passes_dataset_args(monkeypatch):
    from app.api import routes_intelligence

    captured = {}

    class CapturingRunner(FakeRunner):
        async def submit_custom(self, **kwargs):
            captured.update(kwargs)
            return await super().submit_custom(**kwargs)

    monkeypatch.setattr(routes_intelligence, "_runner", lambda: CapturingRunner())
    client = TestClient(app)

    response = client.post(
        "/api/intelligence/tasks",
        json={
            "model_id": "m1",
            "datasets": ["bbh"],
            "dataset_args": {"bbh": {"subset_list": ["boolean_expressions"]}},
        },
    )

    assert response.status_code == 200, response.text
    assert captured["dataset_args"] == {"bbh": {"subset_list": ["boolean_expressions"]}}


def test_intelligence_custom_route_rejects_non_local_dataset(monkeypatch, temp_data_dirs):
    from app.api import routes_intelligence

    monkeypatch.setattr(routes_intelligence, "_runner", lambda: FakeRunner())
    monkeypatch.setattr(routes_intelligence, "local_dataset_metadata", lambda config: {"total": 1, "datasets": {"bbh": {"pretty_name": "BBH"}}})
    client = TestClient(app)

    response = client.post("/api/intelligence/tasks", json={"model_id": "m1", "datasets": ["gsm8k"]})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "dataset_not_local"


def test_evalscope_config_update_preserves_unmanaged_fields(temp_data_dirs):
    data_dir, _ = temp_data_dirs
    config_path = data_dir / "evalscope.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        '{"ignore_dataset_errors": false, "dataset_args": {"bbh": {"subset_list": ["boolean_expressions"]}}}',
        encoding="utf-8",
    )
    client = TestClient(app)

    response = client.put(
        "/api/intelligence/evalscope/config",
        json={
            "judge_model_config_id": "judge-model",
            "judge_generation_config": {"temperature": 0, "max_tokens": 128},
            "judge_worker_num": 2,
            "sandbox_enabled": True,
            "sandbox_type": "docker",
            "sandbox_manager_config": {"base_url": "http://sandbox.local:1234"},
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ignore_dataset_errors"] is False
    assert body["dataset_args"] == {"bbh": {"subset_list": ["boolean_expressions"]}}



def test_intelligence_datasets_endpoint_only_returns_known_local_datasets(temp_data_dirs):
    data_dir, _ = temp_data_dirs
    dataset_root = data_dir / "evalscope_datasets"
    (dataset_root / "bbh" / "boolean_expressions").mkdir(parents=True)
    (dataset_root / "datasets" / "downloads").mkdir(parents=True)
    config_path = data_dir / "evalscope.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps({"datasets_dir": str(dataset_root)}), encoding="utf-8")
    client = TestClient(app)

    response = client.get("/api/intelligence/datasets")

    assert response.status_code == 200, response.text
    body = response.json()
    assert list(body["datasets"].keys()) == ["bbh"]
    assert body["datasets"]["bbh"]["available_local"] is True
    assert body["datasets"]["bbh"]["subsets"] == ["boolean_expressions"]
    assert body["default_datasets"] == ["bbh"]


def test_evalscope_config_api_persists_judge_and_masks_sensitive_sandbox_config(temp_data_dirs):
    client = TestClient(app)

    payload = {
        "judge_model_config_id": "judge-model",
        "judge_generation_config": {"temperature": 0, "max_tokens": 128},
        "judge_worker_num": 2,
        "sandbox_enabled": True,
        "sandbox_type": "docker",
        "sandbox_manager_config": {"base_url": "http://sandbox.local:1234", "api_key": "dummy"},
    }
    saved = client.put("/api/intelligence/evalscope/config", json=payload)
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["judge_model_config_id"] == "judge-model"
    assert body["sandbox_enabled"] is True
    assert body["sandbox_manager_config"]["base_url"] == "http://sandbox.local:1234"
    assert body["sandbox_manager_config"]["api_key"] != "dummy"

    got = client.get("/api/intelligence/evalscope/config")
    assert got.status_code == 200
    assert got.json()["sandbox_manager_config"]["api_key"] == body["sandbox_manager_config"]["api_key"]



def test_sandbox_health_requires_real_health_endpoint(monkeypatch):
    from app.intelligence.evalscope_direct import sandbox_health
    from app.intelligence.schemas import EvalScopeConfig

    class Response:
        def __init__(self, status_code, payload=None):
            self.status_code = status_code
            self._payload = payload or {}

        def json(self):
            return self._payload

    calls = []

    def fake_get(url, timeout):
        calls.append(url)
        if url.endswith("/health"):
            return Response(200, {"healthy": True})
        return Response(404, {"detail": "not found"})

    monkeypatch.setattr("app.intelligence.evalscope_direct.httpx.get", fake_get)

    result = sandbox_health(
        EvalScopeConfig(
            sandbox_enabled=True,
            sandbox_type="docker",
            sandbox_manager_config={"base_url": "http://sandbox.local:1234"},
        )
    )

    assert result["status"] == "ok"
    assert result["http_status"] == 200
    assert result["checked_url"] == "http://sandbox.local:1234/health"
    assert "http://sandbox.local:1234" not in calls


def test_evalscope_sandbox_health_disabled(temp_data_dirs):
    client = TestClient(app)

    response = client.get("/api/intelligence/evalscope/sandbox-health")

    assert response.status_code == 200
    assert response.json()["status"] == "disabled"


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
