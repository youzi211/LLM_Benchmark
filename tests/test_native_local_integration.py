"""Real in-process EvalScope against a loopback fake, with no paid models or downloads."""
import json
import socket
import threading
import time

import pytest
import uvicorn

from app.intelligence.evalscope_direct import EvalScopeIntelligenceExecutor
from app.intelligence.schemas import EvalScopeConfig
from app.stress.evalscope_direct import EvalScopeStressExecutor
from app.stress.schemas import StressRemoteSubmitPayload


@pytest.fixture
def loopback_upstream():
    from examples.fake_openai_server import app
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
    thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(.01)
    assert server.started
    try:
        yield f"http://127.0.0.1:{port}/v1/chat/completions"
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        sock.close()


def test_native_intelligence_local_dataset(tmp_path, monkeypatch, loopback_upstream):
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("MODELSCOPE_OFFLINE", "1")
    monkeypatch.setenv("LLM_BENCHMARK_DATA_DIR", str(tmp_path / "data"))
    dataset = tmp_path / "gsm8k"
    dataset.mkdir()
    (dataset / "README.md").write_text("---\nconfigs:\n- config_name: main\n  data_files:\n  - split: test\n    path: test.jsonl\n---\n", encoding="utf-8")
    (dataset / "test.jsonl").write_text(json.dumps({"question": "What is 1+1?", "answer": "#### 2"}) + "\n", encoding="utf-8")
    executor = EvalScopeIntelligenceExecutor(EvalScopeConfig(outputs_dir=str(tmp_path / "outputs")))
    result = executor.run(task_id="intel_task_local", model="fake", api_url=loopback_upstream, api_key="test",
        datasets=["gsm8k"], limit=1, eval_batch_size=1,
        generation_config={"max_tokens": 16, "temperature": 0}, dataset_args={"gsm8k": {"local_path": str(dataset), "few_shot_num": 0}})
    assert result["status"] == "completed", result.get("errors")
    assert result["results"][0]["report"]["schema_version"] == 2
    from app.intelligence.report_summary import primary_summary
    assert primary_summary(result["results"][0]["report"])["score"] is not None


def test_native_perf_against_loopback(tmp_path, loopback_upstream):
    dataset = tmp_path / "prompts.jsonl"
    dataset.write_text(json.dumps({"prompt": "hello"}) + "\n", encoding="utf-8")
    executor = EvalScopeStressExecutor(EvalScopeConfig(outputs_dir=str(tmp_path / "outputs")))
    result = executor.run(task_id="stress_task_local", payload=StressRemoteSubmitPayload(
        model="fake", url=loopback_upstream, api_key="test", parallel=[1], number=[2],
        dataset="custom", dataset_path=str(dataset), stream=False, max_tokens=16, total_timeout=10))
    from app.stress.runner import _perf_mapping_rows
    rows = _perf_mapping_rows(result)
    assert rows and rows[0]["success"] == 2, result


@pytest.mark.asyncio
async def test_native_three_lane_suite(tmp_path, monkeypatch, loopback_upstream):
    import app.jobs.executor as jobs
    from app.core.models import ModelConfigCreate
    from app.intelligence.config_store import EvalScopeConfigStore
    from app.jobs.store import JobStore
    from app.storage.model_store import ModelStore
    from app.suites.runner import SuiteRunner
    from app.suites.schemas import SuiteDefaultRunRequest

    monkeypatch.setenv("LLM_BENCHMARK_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("MODELSCOPE_OFFLINE", "1")
    monkeypatch.setattr(jobs, "_job_executor", jobs.JobExecutor(store=JobStore()))
    EvalScopeConfigStore().save(EvalScopeConfig(outputs_dir=str(tmp_path / "outputs")))
    ModelStore().create(ModelConfigCreate(id="local-suite", name="本地联调", protocol="chat_completions",
        base_url=loopback_upstream.removesuffix("/chat/completions"), api_key="test", model="fake"))
    dataset = tmp_path / "gsm8k"
    dataset.mkdir()
    (dataset / "README.md").write_text("---\nconfigs:\n- config_name: main\n  data_files:\n  - split: test\n    path: test.jsonl\n---\n", encoding="utf-8")
    (dataset / "test.jsonl").write_text(json.dumps({"question": "What is 1+1?", "answer": "#### 2"}) + "\n", encoding="utf-8")
    prompts = tmp_path / "prompts.jsonl"
    prompts.write_text(json.dumps({"prompt": "hello"}) + "\n", encoding="utf-8")
    runner = SuiteRunner(reports_dir=tmp_path / "reports", poll_interval_seconds=.01)
    suite = await runner.start_default(SuiteDefaultRunRequest(model_id="local-suite", wait_for_completion=True,
        gateway_metric_ids=["connectivity"], intelligence_datasets=["gsm8k"], intelligence_limit=1,
        intelligence_eval_batch_size=1, intelligence_generation_config={"max_tokens": 16, "temperature": 0},
        intelligence_dataset_args={"gsm8k": {"local_path": str(dataset), "few_shot_num": 0}},
        stress_options={"parallel": [1], "number": [2], "dataset": "custom", "dataset_path": str(prompts), "stream": False, "max_tokens": 16},
        timeout_seconds=60))
    assert suite.status == "completed", suite.errors
    assert suite.gateway_task_id and suite.intelligence_task_id and suite.stress_task_id and suite.overview_id
    intelligence = runner.intelligence_task_store.get(suite.intelligence_task_id)
    assert intelligence.execution_snapshot["conditions"]["dataset_args"]["gsm8k"]["local_path"] == str(dataset)
    assert intelligence.normalized_result.dataset_results[0].score == 0
    assert intelligence.normalized_result.dataset_results[0].complete is True
    assert all(step.status == "completed" for step in suite.steps)
    assert list((tmp_path / "reports").rglob("*.md"))
    await jobs.get_job_executor().shutdown()
