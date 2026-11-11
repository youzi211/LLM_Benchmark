from datetime import timedelta

from fastapi.testclient import TestClient

from app.core.models import ModelConfigCreate, TaskResult, MetricResult, utc_now
from app.main import app
from app.storage.model_store import ModelStore
from app.storage.task_store import TaskStore


def setup_models(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_BENCHMARK_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LLM_BENCHMARK_SCHEDULER_DISABLED", "1")
    for id in ["a", "b"]:
        ModelStore().create(ModelConfigCreate(id=id, name="同名模型", model="same", protocol="chat_completions", base_url="http://test", api_key="test-secret"))
    return TestClient(app)


def task(id, model="a", status="completed", days=0):
    now = utc_now() + timedelta(days=days)
    return TaskResult(task_id=id, model_id=model, status=status, plan_id="gateway_acceptance_v1", metric_ids=["connectivity"], started_at=now, finished_at=now,
                      results=[MetricResult(metric_id="connectivity", status="error", summary="不支持")])


def test_latest_success_is_not_limited_or_replaced_by_failure(tmp_path, monkeypatch):
    client = setup_models(tmp_path, monkeypatch)
    TaskStore().save(task("task_success"))
    for i in range(105):
        TaskStore().save(task(f"task_failure_{i}", status="error", days=1))
    data = client.get("/api/model-evaluations/a").json()
    assert data["lanes"]["basic"]["latest_success"]["task_id"] == "task_success"
    assert data["lanes"]["basic"]["latest_attempt"]["status"] == "error"
    assert client.get("/api/model-evaluations").json()["total"] == 2


def test_model_sorting_precedes_pagination_and_keeps_unknown_times_last(tmp_path, monkeypatch):
    from app.storage.intelligence_task_store import IntelligenceTaskStore
    from app.intelligence.schemas import IntelligenceTask
    client = setup_models(tmp_path, monkeypatch)
    TaskStore().save(task("task_recent", model="b", days=2))
    TaskStore().save(task("task_old", model="a"))
    # a 的覆盖更高，b 的执行更新，验证排序不被当前页大小影响。
    item = IntelligenceTask(task_id="intel_task_extra", model_id="a", status="completed", evalscope_base_url="in-process",
        datasets=["math"], created_at=utc_now(), raw_result={"results": [{"dataset": "math", "report": {"score": 0.8}}]})
    IntelligenceTaskStore().save(item)
    for sort_by, expected in [("coverage", "a"), ("last_execution", "b")]:
        response = client.get("/api/model-evaluations", params={"sort_by": sort_by, "order": "desc", "page_size": 1})
        assert response.status_code == 200
        assert response.json()["items"][0]["model_id"] == expected
        assert response.json()["total"] == 2
    assert client.get("/api/model-evaluations", params={"sort_by": "invalid"}).status_code == 422
    assert client.get("/api/model-evaluations", params={"order": "invalid"}).status_code == 422


def test_last_execution_sort_does_not_guess_legacy_timezone(tmp_path, monkeypatch):
    client = setup_models(tmp_path, monkeypatch)
    item = task("task_unknown", model="a", days=10)
    item.started_at = item.started_at.replace(tzinfo=None)
    TaskStore().save(item)
    TaskStore().save(task("task_known", model="b"))
    for order in ["asc", "desc"]:
        data = client.get("/api/model-evaluations", params={"sort_by": "last_execution", "order": order}).json()
        assert [m["model_id"] for m in data["items"]] == ["b", "a"]
        assert data["items"][1]["last_execution_at"] is None


def test_archive_preserves_history_and_blocks_execution(tmp_path, monkeypatch):
    client = setup_models(tmp_path, monkeypatch)
    TaskStore().save(task("task_one"))
    assert client.delete("/api/models/a").status_code == 409
    assert client.post("/api/models/a/archive").status_code == 200
    assert client.get("/api/model-evaluations/a").json()["archived"]
    assert client.post("/api/stress/tasks/default", json={"model_id": "a"}).status_code != 200
    assert client.post("/api/models/a/restore").status_code == 200


def test_comparison_rejects_foreign_task_and_redacts(tmp_path, monkeypatch):
    client = setup_models(tmp_path, monkeypatch)
    TaskStore().save(task("task_b", model="b"))
    response = client.post("/api/model-comparisons", json={"model_ids": ["a", "b"], "task_overrides": {"a": {"basic": "task_b"}}})
    assert response.status_code == 422
    response = client.post("/api/model-comparisons", json={"model_ids": ["a", "b"]})
    assert response.status_code == 200
    assert "test-secret" not in response.text
    assert response.json()["comparability"]["basic"]["status"] == "unknown"


def test_orphan_id_cannot_be_reused(tmp_path, monkeypatch):
    client = setup_models(tmp_path, monkeypatch)
    TaskStore().save(task("task_orphan", model="old"))
    assert client.get("/api/model-evaluations/old").json()["historical_only"]
    response = client.post("/api/models", json={"id": "old", "name": "新", "model": "new", "protocol": "chat_completions", "base_url": "http://test", "api_key": "test"})
    assert response.status_code == 409


def test_complete_open_loop_uses_rates_not_default_parallel(tmp_path, monkeypatch):
    from app.storage.stress_task_store import StressTaskStore
    from app.stress.schemas import StressTask, StressNormalizedResult, StressRunResult
    client = setup_models(tmp_path, monkeypatch)
    StressTaskStore().save(StressTask(task_id="stress_task_open", model_id="a", status="completed", evalscope_base_url="in-process",
        request_config={"open_loop": True, "rate": [2], "parallel": [1, 5, 10, 20]},
        normalized_result=StressNormalizedResult(task_id="stress_task_open", runs=[StressRunResult(rate=2, total=3, success=0, failed=3)])))
    selected = client.get("/api/model-evaluations/a").json()["lanes"]["stress"]["latest_success"]
    assert selected["task_id"] == "stress_task_open"
    assert selected["metrics"][0]["success"] == 0


def test_partial_intelligence_keeps_previous_success(tmp_path, monkeypatch):
    from app.storage.intelligence_task_store import IntelligenceTaskStore
    from app.intelligence.schemas import IntelligenceTask
    client = setup_models(tmp_path, monkeypatch)
    store = IntelligenceTaskStore()
    now = utc_now()
    for id, datasets, days in [("intel_task_old", ["a"], 0), ("intel_task_partial", ["a", "b"], 1)]:
        store.save(IntelligenceTask(task_id=id, model_id="a", evalscope_base_url="in-process", status="completed",
            created_at=now + timedelta(days=days), completed_at=now + timedelta(days=days), datasets=datasets,
            raw_result={"results": [{"dataset": "a", "report": {"score": 0}}]}))
    result = client.get("/api/model-evaluations/a").json()["lanes"]["intelligence"]
    assert result["latest_success"]["task_id"] == "intel_task_old"
    assert result["latest_attempt"]["complete"] is False
    assert result["latest_success"]["metrics"][0]["score"] == 0


def test_comparison_checks_transport_and_timeout(tmp_path, monkeypatch):
    from app.core.snapshots import execution_snapshot
    client = setup_models(tmp_path, monkeypatch)
    for id in ["a", "b"]:
        item = task("task_" + id, model=id)
        model = ModelStore().get(id)
        if id == "b":
            model.timeout_seconds = 1
        item.execution_snapshot = execution_snapshot(model, "basic", {"plan_id": "same"})
        TaskStore().save(item)
    result = client.post("/api/model-comparisons", json={"model_ids": ["a", "b"]}).json()
    assert result["comparability"]["basic"]["status"] == "different"
    assert "timeout_seconds" in result["comparability"]["basic"]["reasons"]


def test_legacy_stress_reads_do_not_write_archives(tmp_path, monkeypatch):
    from app.storage.stress_task_store import StressTaskStore
    from app.stress.schemas import StressTask
    client = setup_models(tmp_path, monkeypatch)
    store = StressTaskStore()
    item = StressTask(task_id="stress_task_legacy", model_id="a", status="completed", evalscope_base_url="in-process",
        request_config={"open_loop": False, "parallel": [1]}, raw_result={"parallel_1_number_1": {"metrics": {"total_requests": 1, "succeed_requests": 0, "failed_requests": 1}}})
    store.save(item)
    path = store.directory / (item.task_id + ".json")
    before = path.read_bytes()
    assert client.get("/api/stress/tasks/stress_task_legacy/result").status_code == 200
    result = client.get("/api/model-evaluations/a").json()["lanes"]["stress"]["latest_success"]
    assert result is not None
    assert result["metrics"][0]["failed"] == 1
    assert path.read_bytes() == before


def test_archive_reports_active_references(tmp_path, monkeypatch):
    client = setup_models(tmp_path, monkeypatch)
    ModelStore().set_analysis_model_id("a")
    response = client.post("/api/models/a/archive")
    assert response.status_code == 409
    assert "analysis_model_id" in response.json()["error"]["details"]["references"]


def test_old_snapshot_and_missing_completion_remain_unknown(tmp_path, monkeypatch):
    client = setup_models(tmp_path, monkeypatch)
    for id in ["a", "b"]:
        item = task("task_" + id, model=id)
        item.finished_at = None
        item.execution_snapshot = {"lane": "basic"}
        TaskStore().save(item)
    result = client.post("/api/model-comparisons", json={"model_ids": ["a", "b"]}).json()
    assert result["comparability"]["basic"]["status"] == "unknown"
    assert result["models"][0]["lanes"]["basic"]["selected"]["completed_at"] is None


def test_suite_only_history_reserves_model_id(tmp_path, monkeypatch):
    from app.suites.store import SuiteRunStore
    from app.suites.schemas import SuiteRun, SuiteDefaultRunRequest
    client = setup_models(tmp_path, monkeypatch)
    SuiteRunStore().save(SuiteRun(model_id="suite-only", request=SuiteDefaultRunRequest(model_id="suite-only")))
    assert client.get("/api/model-evaluations/suite-only").json()["historical_only"] is True
    response = client.post("/api/models", json={"id": "suite-only", "name": "新", "model": "new", "protocol": "chat_completions", "base_url": "http://test", "api_key": "test"})
    assert response.status_code == 409


def test_mixed_legacy_timestamps_are_readable_without_rewriting(tmp_path, monkeypatch):
    client = setup_models(tmp_path, monkeypatch)
    older = task("task_legacy_time")
    older.finished_at = older.finished_at.replace(tzinfo=None)
    TaskStore().save(older)
    TaskStore().save(task("task_aware_time", days=2))
    path = TaskStore().directory / (older.task_id + ".json")
    before = path.read_bytes()
    data = client.get("/api/model-evaluations/a").json()
    assert data["lanes"]["basic"]["latest_success"]["task_id"] == "task_aware_time"
    assert client.get("/api/model-evaluations/a/history").status_code == 200
    assert path.read_bytes() == before


def test_missing_historical_time_does_not_become_current_time(tmp_path, monkeypatch):
    from app.storage.file_utils import write_json_file_atomic
    from app.storage.intelligence_task_store import IntelligenceTaskStore
    from app.intelligence.schemas import IntelligenceTask
    client = setup_models(tmp_path, monkeypatch)
    payload = IntelligenceTask(task_id="intel_task_no_time", model_id="a", status="completed", evalscope_base_url="in-process").model_dump(mode="json")
    payload.pop("created_at", None)
    payload.pop("completed_at", None)
    write_json_file_atomic(IntelligenceTaskStore().directory / "intel_task_no_time.json", payload)
    item = client.get("/api/model-evaluations/a/history").json()["items"][0]
    assert item["created_at"] is None and item["completed_at"] is None
    assert client.get("/api/model-evaluations/a").json()["last_execution_at"] is None


def test_legacy_stress_mixed_time_preserves_history_and_id(tmp_path, monkeypatch):
    from app.storage.stress_task_store import StressTaskStore
    from app.stress.schemas import StressTask
    client = setup_models(tmp_path, monkeypatch)
    now = utc_now()
    item = StressTask(task_id="stress_task_mixed_time", model_id="legacy-time", evalscope_base_url="in-process",
        status="completed", created_at=now, completed_at=(now + timedelta(seconds=5)).astimezone().replace(tzinfo=None))
    store = StressTaskStore()
    store.save(item)
    path = store.directory / (item.task_id + ".json")
    before = path.read_bytes()
    assert store.get(item.task_id).duration_ms == 5000
    assert client.get("/api/model-evaluations/legacy-time").status_code == 200
    assert path.read_bytes() == before
    response = client.post("/api/models", json={"id": "legacy-time", "name": "new", "model": "new", "protocol": "chat_completions", "base_url": "http://test", "api_key": "test"})
    assert response.status_code == 409
