import math
from pathlib import Path

import pytest

from fastapi.testclient import TestClient

from app.main import app
from app.stress.schemas import StressNormalizedResult, StressRunResult, StressTask


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
    assert "/api/stress/tasks/{task_id}/raw-result" in paths
    assert "/api/stress/tasks/{task_id}/artifacts" in paths
    assert "/api/stress/tasks/{task_id}/artifacts/{artifact_path}" in paths


def test_stress_datasets_default_is_available_when_local_default_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_BENCHMARK_STRESS_DATASETS_DIR", str(tmp_path / "missing_stress_datasets"))
    client = TestClient(app)

    response = client.get("/api/stress/datasets")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["default_dataset"] in body["datasets"]
    assert body["default_dataset"] == "speed_benchmark"


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


def test_stress_result_sanitizes_non_finite_numbers(monkeypatch):
    from app.api import routes_stress

    class NonFiniteRunner(FakeRunner):
        async def fetch_result(self, task_id: str):
            return StressTask(
                task_id=task_id,
                model_id="m1",
                protocol="chat_completions",
                evalscope_base_url="in-process",
                status="completed",
                raw_result={
                    "summary": {"best_req_throughput": math.nan},
                    "runs": [{"request_throughput": math.inf, "avg_latency": -math.inf}],
                },
                normalized_result=StressNormalizedResult(
                    task_id=task_id,
                    summary={"best_req_throughput": math.nan},
                    runs=[StressRunResult(request_throughput=math.inf, avg_latency_seconds=-math.inf)],
                ),
            )

    monkeypatch.setattr(routes_stress, "_runner", lambda: NonFiniteRunner())
    client = TestClient(app)

    response = client.get("/api/stress/tasks/some/result")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["raw_result"]["summary"]["best_req_throughput"] is None
    assert payload["raw_result"]["runs"][0]["request_throughput"] is None
    assert payload["raw_result"]["runs"][0]["avg_latency"] is None
    assert payload["normalized_result"]["summary"]["best_req_throughput"] is None
    assert payload["normalized_result"]["runs"][0]["request_throughput"] is None
    assert payload["normalized_result"]["runs"][0]["avg_latency_seconds"] is None


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


def test_stress_raw_result_and_artifact_downloads(tmp_path, monkeypatch):
    from app.api import routes_stress

    output_dir = tmp_path / "output"
    nested = output_dir / "run"
    nested.mkdir(parents=True)
    (nested / "summary.json").write_text('{"ok": true}', encoding="utf-8")
    task = StressTask(
        task_id="stress-task",
        model_id="m1",
        evalscope_base_url="in-process",
        raw_result={"status": "completed", "secret": None},
        raw_output_dir=str(output_dir),
    )

    class Store:
        def get(self, task_id):
            return task if task_id == task.task_id else None

    monkeypatch.setattr(routes_stress, "StressTaskStore", lambda: Store())
    client = TestClient(app)

    raw = client.get("/api/stress/tasks/stress-task/raw-result")
    assert raw.status_code == 200
    assert raw.json()["status"] == "completed"
    assert "attachment" in raw.headers["content-disposition"]

    listing = client.get("/api/stress/tasks/stress-task/artifacts")
    assert listing.status_code == 200
    assert listing.json()["artifacts"][0]["path"] == "run/summary.json"

    downloaded = client.get("/api/stress/tasks/stress-task/artifacts/run/summary.json")
    assert downloaded.status_code == 200
    assert downloaded.json() == {"ok": True}


def test_stress_artifact_path_is_confined_to_task_directory(tmp_path):
    from app.stress.artifacts import resolve_task_artifact

    output_dir = tmp_path / "output"
    output_dir.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("private", encoding="utf-8")

    with pytest.raises(ValueError, match="outside task output directory"):
        resolve_task_artifact(output_dir, "../outside.txt")
    with pytest.raises(ValueError, match="relative"):
        resolve_task_artifact(output_dir, str(outside.resolve()))

    link = output_dir / "escape.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        return
    with pytest.raises(ValueError, match="outside task output directory"):
        resolve_task_artifact(output_dir, "escape.txt")
