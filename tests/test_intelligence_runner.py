import pytest

from app.core.models import ModelConfigCreate
from app.intelligence.runner import IntelligenceRunner
from app.storage.intelligence_task_store import IntelligenceTaskStore
from app.storage.model_store import ModelStore


class FakeIntelligenceExecutor:
    def __init__(self):
        self.calls = []

    def run(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "task_id": kwargs["task_id"],
            "model": kwargs["model"],
            "datasets": kwargs["datasets"],
            "status": "completed",
            "results": [
                {"dataset": dataset, "report": {"dataset_name": dataset.upper(), "score": 80.0, "metrics": [{"name": "acc", "score": 0.8}]}}
                for dataset in kwargs["datasets"]
            ],
            "report_table": "table",
            "completed_at": "2026-08-06T12:00:00+00:00",
        }


def _model_store(path, protocol="chat_completions"):
    store = ModelStore(path)
    store.create(ModelConfigCreate(
        id="m1",
        name="模型一",
        protocol=protocol,
        base_url="http://model.local/v1",
        api_key="dummy-api-key-should-not-leak",
        model="upstream-model",
    ))
    return store


@pytest.mark.asyncio
async def test_intelligence_runner_runs_evalscope_in_process_and_generates_report(tmp_path):
    executor = FakeIntelligenceExecutor()
    runner = IntelligenceRunner(
        model_store=_model_store(tmp_path / "models.json"),
        task_store=IntelligenceTaskStore(tmp_path / "intelligence_tasks"),
        executor=executor,
        reports_dir=tmp_path / "reports",
        run_in_background=False,
    )

    task = await runner.submit_custom(model_id="m1", datasets=["gsm8k"], limit=3, eval_batch_size=2)

    assert task.evalscope_base_url == "in-process"
    assert task.status == "completed"
    assert executor.calls[0]["api_url"] == "http://model.local/v1/chat/completions"
    assert executor.calls[0]["api_key"] == "dummy-api-key-should-not-leak"
    assert executor.calls[0]["limit"] == 3
    assert executor.calls[0]["eval_batch_size"] == 2
    assert task.normalized_result.dataset_results[0].dataset == "gsm8k"
    assert task.normalized_result.dataset_results[0].score == 80.0
    assert task.normalized_result.category_summaries
    assert task.report_path is not None
    report_text = open(task.report_path, encoding="utf-8").read()
    assert "dummy-api-key-should-not-leak" not in report_text
    assert "GSM8K" in report_text


@pytest.mark.asyncio
async def test_intelligence_runner_maps_responses_endpoint(tmp_path):
    executor = FakeIntelligenceExecutor()
    runner = IntelligenceRunner(
        model_store=_model_store(tmp_path / "models.json", protocol="responses"),
        task_store=IntelligenceTaskStore(tmp_path / "intelligence_tasks"),
        executor=executor,
        reports_dir=tmp_path / "reports",
        run_in_background=False,
    )

    await runner.submit_custom(model_id="m1", datasets=["gsm8k"])

    assert executor.calls[0]["api_url"] == "http://model.local/v1/responses"


@pytest.mark.asyncio
async def test_intelligence_runner_default_uses_curated_dataset_suite(tmp_path):
    executor = FakeIntelligenceExecutor()
    runner = IntelligenceRunner(
        model_store=_model_store(tmp_path / "models.json"),
        task_store=IntelligenceTaskStore(tmp_path / "intelligence_tasks"),
        executor=executor,
        reports_dir=tmp_path / "reports",
        run_in_background=False,
    )

    task = await runner.submit_default("m1")

    assert "humaneval" in task.datasets
    assert "gsm8k" in task.datasets
    assert executor.calls[0]["datasets"] == task.datasets
