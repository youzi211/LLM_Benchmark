import pytest

from app.core.models import ModelConfigCreate
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



def test_stress_runner_resolves_local_jsonl_dataset_path(tmp_path, monkeypatch):
    dataset_root = tmp_path / "stress_datasets"
    dataset_root.mkdir()
    dataset_file = dataset_root / "openqa.jsonl"
    dataset_file.write_text('{"question":"hello"}\n', encoding="utf-8")
    monkeypatch.setattr(stress_runner_module, "STRESS_DATASETS_DIR", dataset_root)
    runner = StressRunner(
        model_store=_model_store(tmp_path / "models.json"),
        task_store=StressTaskStore(tmp_path / "stress_tasks"),
        executor=FakeStressExecutor(),
        reports_dir=tmp_path / "reports",
        run_in_background=False,
    )

    resolved = runner._resolve_dataset_path(stress_runner_module.StressDefaultRunRequest(model_id="m1", dataset="openqa"))

    assert resolved == str(dataset_file)
