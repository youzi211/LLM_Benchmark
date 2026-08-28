import asyncio
import threading

import pytest

from app.core.models import ModelConfigCreate
from app.evalscope_defaults import DEFAULT_STRESS_DATASET
from app.jobs.executor import JobExecutor
from app.jobs.store import JobStore
from app.storage.model_store import ModelStore
from app.storage.stress_task_store import StressTaskStore
from app.stress import runner as stress_runner_module
from app.stress.runner import StressRunner


class FakeStressExecutor:
    def __init__(self, result=None):
        self.submitted_payload = None
        self.result = result or {
            "task_id": "stress-direct-1",
            "status": "completed",
            "summary": {"best_req_throughput": 9.5},
            "runs": [{"parallel": 1, "number": 2, "total": 2, "success": 2, "failed": 0, "request_throughput": 9.5}],
            "errors": [],
        }

    def run(self, *, task_id, payload):
        self.submitted_payload = payload.model_dump(mode="json")
        return {**self.result, "task_id": task_id}


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
async def test_stress_runner_calls_evalscope_in_process_and_writes_result(tmp_path):
    executor = FakeStressExecutor()
    runner = StressRunner(
        model_store=_model_store(tmp_path / "models.json"),
        task_store=StressTaskStore(tmp_path / "stress_tasks"),
        executor=executor,
        reports_dir=tmp_path / "reports",
        run_in_background=False,
    )

    submitted = await runner.submit_default("m1")

    assert submitted.evalscope_base_url == "in-process"
    assert executor.submitted_payload["api"] == "openai"
    assert executor.submitted_payload["url"] == "http://model.local/v1/chat/completions"
    assert executor.submitted_payload["api_key"] == "dummy-api-key-should-not-leak"
    assert executor.submitted_payload["stream"] is True

    fetched = await runner.fetch_result(submitted.task_id)
    assert fetched.status == "completed"
    assert fetched.normalized_result.summary["best_req_throughput"] == 9.5
    assert fetched.report_path is not None
    assert "dummy-api-key-should-not-leak" not in open(fetched.report_path, encoding="utf-8").read()
    assert "api_key" not in fetched.request_config


@pytest.mark.asyncio
async def test_stress_runner_maps_responses_protocol(tmp_path):
    executor = FakeStressExecutor()
    runner = StressRunner(
        model_store=_model_store(tmp_path / "models.json", protocol="responses"),
        task_store=StressTaskStore(tmp_path / "stress_tasks"),
        executor=executor,
        reports_dir=tmp_path / "reports",
        run_in_background=False,
    )

    await runner.submit_default("m1")

    assert executor.submitted_payload["api"] == "openai_responses"
    assert executor.submitted_payload["url"] == "http://model.local/v1/responses"


@pytest.mark.asyncio
async def test_stress_runner_normalizes_evalscope_perf_raw_mapping(tmp_path):
    executor = FakeStressExecutor(result={
        "status": "completed",
        "raw_result": {
            "parallel_1_number_2": {
                "metrics": {
                    "concurrency": 1,
                    "total_requests": 2,
                    "succeed_requests": 2,
                    "failed_requests": 0,
                    "request_throughput": 4.2,
                    "output_token_throughput": 12.5,
                    "total_token_throughput": 42.0,
                    "avg_latency": 0.25,
                    "avg_ttft": 120.0,
                    "avg_tpot": 11.0,
                },
                "percentiles": {
                    "rows": [
                        {"percentile": "50%", "latency": 0.2, "ttft": 100.0},
                        {"percentile": "95%", "latency": 0.4, "ttft": 200.0},
                        {"percentile": "99%", "latency": 0.5, "ttft": 300.0},
                    ]
                },
            }
        },
    })
    runner = StressRunner(
        model_store=_model_store(tmp_path / "models.json"),
        task_store=StressTaskStore(tmp_path / "stress_tasks"),
        executor=executor,
        reports_dir=tmp_path / "reports",
        run_in_background=False,
    )

    task = await runner.submit_default("m1")

    run = task.normalized_result.runs[0]
    assert run.parallel == 1
    assert run.total == 2
    assert run.success == 2
    assert run.failed == 0
    assert run.request_throughput == 4.2
    assert run.output_throughput == 12.5
    assert run.p95_latency_seconds == 0.4
    assert task.normalized_result.summary["best_output_throughput"] == 12.5



@pytest.mark.asyncio
async def test_stress_runner_default_falls_back_to_non_download_dataset(tmp_path, monkeypatch):
    missing_root = tmp_path / "missing_stress_datasets"
    monkeypatch.setattr(stress_runner_module, "STRESS_DATASETS_DIR", missing_root)
    executor = FakeStressExecutor()
    runner = StressRunner(
        model_store=_model_store(tmp_path / "models.json"),
        task_store=StressTaskStore(tmp_path / "stress_tasks"),
        executor=executor,
        reports_dir=tmp_path / "reports",
        run_in_background=False,
    )

    await runner.submit_default("m1")

    assert executor.submitted_payload["dataset"] == "speed_benchmark"
    assert executor.submitted_payload.get("dataset_path") is None


def test_stress_runner_rejects_explicit_missing_local_dataset(tmp_path, monkeypatch):
    missing_root = tmp_path / "missing_stress_datasets"
    monkeypatch.setattr(stress_runner_module, "STRESS_DATASETS_DIR", missing_root)
    runner = StressRunner(
        model_store=_model_store(tmp_path / "models.json"),
        task_store=StressTaskStore(tmp_path / "stress_tasks"),
        executor=FakeStressExecutor(),
        reports_dir=tmp_path / "reports",
        run_in_background=False,
    )

    with pytest.raises(ValueError, match="stress_dataset_not_local:longalpaca"):
        runner._build_payload(runner.model_store.get("m1"), stress_runner_module.StressDefaultRunRequest(model_id="m1", dataset=DEFAULT_STRESS_DATASET))


def test_stress_runner_resolves_local_jsonl_dataset_path(tmp_path, monkeypatch):
    dataset_root = tmp_path / "stress_datasets"
    dataset_root.mkdir()
    dataset_file = dataset_root / f"{DEFAULT_STRESS_DATASET}.jsonl"
    dataset_file.write_text('{"question":"hello"}\n', encoding="utf-8")
    monkeypatch.setattr(stress_runner_module, "STRESS_DATASETS_DIR", dataset_root)
    runner = StressRunner(
        model_store=_model_store(tmp_path / "models.json"),
        task_store=StressTaskStore(tmp_path / "stress_tasks"),
        executor=FakeStressExecutor(),
        reports_dir=tmp_path / "reports",
        run_in_background=False,
    )

    resolved = runner._resolve_dataset_path(stress_runner_module.StressDefaultRunRequest(model_id="m1", dataset=DEFAULT_STRESS_DATASET))

    assert resolved == str(dataset_file)


@pytest.mark.asyncio
async def test_stress_runner_resolves_local_path_for_default_dataset(tmp_path, monkeypatch):
    dataset_root = tmp_path / "stress_datasets"
    dataset_root.mkdir()
    dataset_file = dataset_root / f"{DEFAULT_STRESS_DATASET}.jsonl"
    dataset_file.write_text('{"question":"hello"}\n', encoding="utf-8")
    monkeypatch.setattr(stress_runner_module, "STRESS_DATASETS_DIR", dataset_root)
    executor = FakeStressExecutor()
    runner = StressRunner(
        model_store=_model_store(tmp_path / "models.json"),
        task_store=StressTaskStore(tmp_path / "stress_tasks"),
        executor=executor,
        reports_dir=tmp_path / "reports",
        run_in_background=False,
    )

    await runner.submit_default("m1")

    assert executor.submitted_payload["dataset"] == DEFAULT_STRESS_DATASET
    assert executor.submitted_payload["dataset_path"] == str(dataset_file)


@pytest.mark.asyncio
async def test_stress_runner_background_uses_job_executor(tmp_path, monkeypatch):
    executor = FakeStressExecutor()
    submissions = []

    class FakeJobExecutor:
        def submit_sync(self, *, job_type: str, target_id: str, payload: dict, func):
            submissions.append({"job_type": job_type, "target_id": target_id, "payload": payload, "func": func})
            return type("Job", (), {"job_id": "job_stress"})()

    monkeypatch.setattr(stress_runner_module, "get_job_executor", lambda: FakeJobExecutor())
    runner = StressRunner(
        model_store=_model_store(tmp_path / "models.json"),
        task_store=StressTaskStore(tmp_path / "stress_tasks"),
        executor=executor,
        reports_dir=tmp_path / "reports",
        run_in_background=True,
    )

    task = await runner.submit_default("m1")

    assert task.status == "pending"
    assert submissions == [{"job_type": "stress", "target_id": task.task_id, "payload": {"task_id": task.task_id}, "func": submissions[0]["func"]}]
    assert executor.submitted_payload is None


class SlowStressExecutor:
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()

    def run(self, *, task_id, payload):
        self.started.set()
        self.release.wait(timeout=1)
        return {
            "task_id": task_id,
            "status": "completed",
            "summary": {"best_req_throughput": 1.0},
            "runs": [],
            "errors": [],
        }


@pytest.mark.asyncio
async def test_stress_runner_cancel_marks_task_and_prevents_late_overwrite(tmp_path, monkeypatch):
    job_executor = JobExecutor(store=JobStore(tmp_path / "jobs"), max_concurrency=1)
    monkeypatch.setattr("app.stress.runner.get_job_executor", lambda: job_executor)
    executor = SlowStressExecutor()
    task_store = StressTaskStore(tmp_path / "stress_tasks")
    runner = StressRunner(
        model_store=_model_store(tmp_path / "models.json"),
        task_store=task_store,
        executor=executor,
        reports_dir=tmp_path / "reports",
        run_in_background=True,
    )

    task = await runner.submit_default("m1")
    assert await asyncio.to_thread(executor.started.wait, 1)

    cancelled = await runner.cancel(task.task_id)

    assert cancelled.status == "interrupted"
    assert cancelled.progress == "任务已取消"
    job = next(item for item in job_executor.store.list(limit=10) if item.target_id == task.task_id)
    assert job.status == "interrupted"
    executor.release.set()
    await job_executor.wait(job.job_id, timeout=1)
    assert task_store.get(task.task_id).status == "interrupted"
