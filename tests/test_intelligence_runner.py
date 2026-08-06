import httpx
import pytest

from app.core.models import ModelConfigCreate
from app.intelligence.evalscope_client import EvalScopeClient
from app.intelligence.runner import IntelligenceRunner, new_intelligence_task_id
from app.intelligence.schemas import EvalScopeConfig
from app.storage.intelligence_task_store import IntelligenceTaskStore
from app.storage.model_store import ModelStore


def _model_store(path):
    store = ModelStore(path)
    store.create(ModelConfigCreate(id="m1", name="模型一", protocol="chat_completions", base_url="http://model/v1", api_key="test-key", model="upstream-model"))
    return store


@pytest.mark.asyncio
async def test_intelligence_runner_submit_refresh_and_fetch_result(tmp_path):
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/eval/default"):
            return httpx.Response(200, json={"task_id": "eval-1", "status": "pending", "message": "ok"})
        if request.url.path.endswith("/tasks/eval-1/result"):
            return httpx.Response(200, json={
                "task_id": "eval-1",
                "model": "upstream-model",
                "datasets": ["gsm8k"],
                "status": "completed",
                "results": [{"dataset": "gsm8k", "report": {"score": 0.9, "metrics": [{"name": "mean_acc"}]}}],
                "report_table": "table",
                "completed_at": "2026-08-06T01:45:20+00:00",
                "error": None,
            })
        if request.url.path.endswith("/tasks/eval-1"):
            return httpx.Response(200, json={"task_id": "eval-1", "status": "completed", "progress": "评测完成 (1/1)", "datasets": ["gsm8k"]})
        if request.url.path.endswith("/datasets/local"):
            return httpx.Response(200, json={"datasets": {"gsm8k": {"pretty_name": "GSM8K", "categories": ["Math", "Reasoning"], "needs_judge": False}}})
        if request.url.path.endswith("/judge-config"):
            return httpx.Response(200, json={"configured": True, "model_id": "judge"})
        return httpx.Response(404, json={"detail": "missing"})

    runner = IntelligenceRunner(
        model_store=_model_store(tmp_path / "models.json"),
        task_store=IntelligenceTaskStore(tmp_path / "tasks"),
        client=EvalScopeClient(EvalScopeConfig(base_url="http://evalscope/api/v1"), transport=httpx.MockTransport(handler)),
        reports_dir=tmp_path / "reports",
    )

    submitted = await runner.submit_default("m1")
    assert submitted.evalscope_task_id == "eval-1"
    assert submitted.upstream_model_name == "upstream-model"

    fetched = await runner.fetch_result(submitted.task_id)
    assert fetched is not None
    assert fetched.status == "completed"
    assert fetched.normalized_result is not None
    assert fetched.normalized_result.dataset_results[0].pretty_name == "GSM8K"
    assert fetched.normalized_result.category_summaries[0].average_score == 0.9
    assert fetched.report_path is not None


@pytest.mark.asyncio
async def test_intelligence_runner_does_not_fetch_result_until_terminal(tmp_path):
    called_result = False

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called_result
        if request.url.path.endswith("/eval/default"):
            return httpx.Response(200, json={"task_id": "eval-1", "status": "pending"})
        if request.url.path.endswith("/tasks/eval-1/result"):
            called_result = True
            return httpx.Response(200, json={})
        if request.url.path.endswith("/tasks/eval-1"):
            return httpx.Response(200, json={"task_id": "eval-1", "status": "running", "progress": "正在评测 (1/1): gsm8k"})
        return httpx.Response(200, json={})

    runner = IntelligenceRunner(
        model_store=_model_store(tmp_path / "models.json"),
        task_store=IntelligenceTaskStore(tmp_path / "tasks"),
        client=EvalScopeClient(EvalScopeConfig(base_url="http://evalscope/api/v1"), transport=httpx.MockTransport(handler)),
        reports_dir=tmp_path / "reports",
    )
    submitted = await runner.submit_default("m1")

    task = await runner.fetch_result(submitted.task_id)

    assert task is not None
    assert task.status == "running"
    assert called_result is False


def test_new_intelligence_task_id_format():
    assert new_intelligence_task_id().startswith("intel_task_")
