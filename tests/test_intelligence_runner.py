import asyncio
import json
import threading

import pytest

from app.core.models import ModelConfigCreate
from app.intelligence.config_store import EvalScopeConfigStore
from app.intelligence.runner import IntelligenceRunner
from app.intelligence.schemas import EvalScopeConfig, IntelligenceTask
from app.jobs.executor import JobExecutor
from app.jobs.store import JobStore
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


def _model_store(path, protocol="chat_completions", *, with_analysis_judge=False):
    store = ModelStore(path)
    store.create(ModelConfigCreate(
        id="m1",
        name="模型一",
        protocol=protocol,
        base_url="http://model.local/v1",
        api_key="dummy-api-key-should-not-leak",
        model="upstream-model",
    ))
    if with_analysis_judge:
        store.create(ModelConfigCreate(
            id="judge-model",
            name="内置 Judge",
            protocol="chat_completions",
            base_url="http://judge.local/v1",
            api_key="dummy-judge-key-should-not-leak",
            model="judge-upstream-model",
        ))
        store.set_analysis_model_id("judge-model")
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
async def test_intelligence_runner_refreshes_evalscope_progress_file(tmp_path):
    outputs_dir = tmp_path / "outputs"
    task_store = IntelligenceTaskStore(tmp_path / "intelligence_tasks")
    config_store = EvalScopeConfigStore(tmp_path / "evalscope.json")
    config_store.save(EvalScopeConfig(outputs_dir=str(outputs_dir)))
    task = IntelligenceTask(
        task_id="intel_task_progress",
        model_id="m1",
        evalscope_base_url="in-process",
        datasets=["live_code_bench", "gsm8k"],
        status="running",
        raw_output_dir=str(outputs_dir / "intelligence" / "intel_task_progress"),
    )
    task_store.save(task)
    progress_dir = outputs_dir / "intelligence" / "intel_task_progress" / "live_code_bench" / "20260828_120000"
    progress_dir.mkdir(parents=True)
    (progress_dir / "progress.json").write_text(
        json.dumps(
            {
                "status": "running",
                "pipeline": "eval",
                "total_count": 200,
                "processed_count": 75,
                "percent": 37.5,
                "updated_at": "2026-08-28T12:00:00+08:00",
            }
        ),
        encoding="utf-8",
    )
    runner = IntelligenceRunner(
        model_store=_model_store(tmp_path / "models.json"),
        task_store=task_store,
        config_store=config_store,
        executor=FakeIntelligenceExecutor(),
        reports_dir=tmp_path / "reports",
        run_in_background=False,
    )

    refreshed = await runner.refresh_status("intel_task_progress")

    assert refreshed is not None
    assert refreshed.progress_detail is not None
    assert refreshed.progress_detail.current_dataset == "live_code_bench"
    assert refreshed.progress_detail.processed_count == 75
    assert refreshed.progress_detail.total_count == 200
    assert refreshed.progress_detail.percent == 37.5
    assert refreshed.progress_detail.overall_percent == 18.75
    assert "75/200" in refreshed.progress


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


@pytest.mark.asyncio
async def test_intelligence_runner_uses_analysis_model_as_builtin_judge(tmp_path):
    executor = FakeIntelligenceExecutor()
    runner = IntelligenceRunner(
        model_store=_model_store(tmp_path / "models.json", with_analysis_judge=True),
        task_store=IntelligenceTaskStore(tmp_path / "intelligence_tasks"),
        executor=executor,
        reports_dir=tmp_path / "reports",
        run_in_background=False,
    )

    task = await runner.submit_custom(model_id="m1", datasets=["simple_qa"])

    judge_args = executor.calls[0]["judge_model_args"]
    assert judge_args["model_id"] == "judge-upstream-model"
    assert judge_args["api_url"] == "http://judge.local/v1/chat/completions"
    assert judge_args["api_key"] == "dummy-judge-key-should-not-leak"
    assert task.raw_submit_response["judge"]["source"] == "analysis_model"
    report_text = open(task.report_path, encoding="utf-8").read()
    assert "dummy-judge-key-should-not-leak" not in report_text
    assert "simple_qa" in report_text


@pytest.mark.asyncio
async def test_intelligence_runner_rejects_judge_dataset_without_builtin_judge(tmp_path):
    executor = FakeIntelligenceExecutor()
    runner = IntelligenceRunner(
        model_store=_model_store(tmp_path / "models.json"),
        task_store=IntelligenceTaskStore(tmp_path / "intelligence_tasks"),
        executor=executor,
        reports_dir=tmp_path / "reports",
        run_in_background=False,
    )

    with pytest.raises(ValueError, match="judge_required:simple_qa"):
        await runner.submit_custom(model_id="m1", datasets=["simple_qa"])

    assert executor.calls == []


@pytest.mark.asyncio
async def test_intelligence_runner_background_uses_job_executor(tmp_path, monkeypatch):
    from app.intelligence import runner as intelligence_runner_module

    class FakeExecutor:
        def __init__(self):
            self.called = False

        def run(self, **kwargs):
            self.called = True
            return {"status": "completed", "task_id": kwargs["task_id"], "model": kwargs["model"], "datasets": kwargs["datasets"], "results": []}

    submissions = []

    class FakeJobExecutor:
        def submit_sync(self, *, job_type: str, target_id: str, payload: dict, func):
            submissions.append({"job_type": job_type, "target_id": target_id, "payload": payload, "func": func})
            return type("Job", (), {"job_id": "job_intel"})()

    model_store = ModelStore(tmp_path / "models.json")
    model_store.create(ModelConfigCreate(id="m1", name="Model", protocol="chat_completions", base_url="http://model/v1", api_key="dummy", model="upstream"))
    fake_executor = FakeExecutor()
    monkeypatch.setattr(intelligence_runner_module, "get_job_executor", lambda: FakeJobExecutor())
    runner = IntelligenceRunner(
        model_store=model_store,
        task_store=IntelligenceTaskStore(tmp_path / "intelligence_tasks"),
        executor=fake_executor,
        reports_dir=tmp_path / "reports",
        run_in_background=True,
    )

    task = await runner.submit_custom(model_id="m1", datasets=["gsm8k"], limit=1)

    assert task.status == "pending"
    assert submissions == [{"job_type": "intelligence", "target_id": task.task_id, "payload": {"task_id": task.task_id}, "func": submissions[0]["func"]}]
    assert fake_executor.called is False


class SlowIntelligenceExecutor:
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()

    def run(self, **kwargs):
        self.started.set()
        self.release.wait(timeout=1)
        return {
            "task_id": kwargs["task_id"],
            "model": kwargs["model"],
            "datasets": kwargs["datasets"],
            "status": "completed",
            "results": [],
            "completed_at": "2026-08-06T12:00:00+00:00",
        }


@pytest.mark.asyncio
async def test_intelligence_runner_cancel_marks_task_and_prevents_late_overwrite(tmp_path, monkeypatch):
    job_executor = JobExecutor(store=JobStore(tmp_path / "jobs"), max_concurrency=1)
    monkeypatch.setattr("app.intelligence.runner.get_job_executor", lambda: job_executor)
    executor = SlowIntelligenceExecutor()
    task_store = IntelligenceTaskStore(tmp_path / "intelligence_tasks")
    runner = IntelligenceRunner(
        model_store=_model_store(tmp_path / "models.json"),
        task_store=task_store,
        executor=executor,
        reports_dir=tmp_path / "reports",
        run_in_background=True,
    )

    task = await runner.submit_custom(model_id="m1", datasets=["gsm8k"], limit=1)
    assert await asyncio.to_thread(executor.started.wait, 1)

    cancelled = await runner.cancel(task.task_id)

    assert cancelled.status == "interrupted"
    assert cancelled.progress == "任务已取消"
    job = next(item for item in job_executor.store.list(limit=10) if item.target_id == task.task_id)
    assert job.status == "interrupted"
    executor.release.set()
    await job_executor.wait(job.job_id, timeout=1)
    assert task_store.get(task.task_id).status == "interrupted"


@pytest.mark.asyncio
async def test_intelligence_runner_cancel_completed_is_noop(tmp_path):
    executor = FakeIntelligenceExecutor()
    task_store = IntelligenceTaskStore(tmp_path / "intelligence_tasks")
    runner = IntelligenceRunner(
        model_store=_model_store(tmp_path / "models.json"),
        task_store=task_store,
        executor=executor,
        reports_dir=tmp_path / "reports",
        run_in_background=False,
    )
    task = await runner.submit_custom(model_id="m1", datasets=["gsm8k"], limit=1)

    cancelled = await runner.cancel(task.task_id)

    assert cancelled.status == "completed"
    assert task_store.get(task.task_id).status == "completed"
