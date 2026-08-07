import sys
import types

from app.intelligence.evalscope_direct import (
    EvalScopeDirectError,
    EvalScopeIntelligenceExecutor,
    dataset_metadata,
    judge_config_status,
)
from app.intelligence.schemas import EvalScopeConfig
from app.stress.evalscope_direct import EvalScopeStressExecutor
from app.stress.schemas import StressRemoteSubmitPayload


def test_evalscope_config_is_in_process_and_ignores_legacy_base_url():
    config = EvalScopeConfig.model_validate({"base_url": "http://legacy-evalscope/api/v1/", "outputs_dir": "outputs/evalscope/"})

    assert not hasattr(config, "base_url")
    assert config.outputs_dir == "outputs/evalscope"
    assert dataset_metadata(config)["default_datasets"]


def test_judge_config_status_does_not_expose_api_key():
    status = judge_config_status(
        EvalScopeConfig(judge_model_config_id="judge-model"),
        configured=True,
        model_config_id="judge-model",
        model_name="judge-upstream",
        source="analysis_model",
        required_datasets=["simple_qa"],
    )

    assert status["configured"] is True
    assert status["model_config_id"] == "judge-model"
    assert status["model_id"] == "judge-upstream"
    assert status["source"] == "analysis_model"
    assert "api_key" not in status
    assert "dummy-secret-key" not in str(status)


def test_intelligence_executor_enables_remote_sandbox_for_mbpp(tmp_path):
    executor = EvalScopeIntelligenceExecutor(
        EvalScopeConfig(
            outputs_dir=str(tmp_path / "outputs"),
            sandbox_enabled=True,
            sandbox_type="docker",
            sandbox_manager_config={"base_url": "http://sandbox.local:1234"},
        )
    )

    data = executor._task_config_data(
        model="demo",
        api_url="http://model/v1/chat/completions",
        api_key="dummy",
        dataset="mbpp",
        local_paths={},
        limit=2,
        eval_batch_size=1,
        generation_config=None,
        work_dir=str(tmp_path / "work"),
        judge_model_args=None,
    )

    assert data["use_sandbox"] is True
    assert data["sandbox_type"] == "docker"
    assert data["sandbox_manager_config"] == {"base_url": "http://sandbox.local:1234"}


def test_intelligence_executor_requires_sandbox_for_code_execution_datasets(tmp_path):
    executor = EvalScopeIntelligenceExecutor(EvalScopeConfig(outputs_dir=str(tmp_path / "outputs")))

    try:
        executor._task_config_data(
            model="demo",
            api_url="http://model/v1/chat/completions",
            api_key="dummy",
            dataset="mbpp_plus",
            local_paths={},
            limit=1,
            eval_batch_size=1,
            generation_config=None,
            work_dir=str(tmp_path / "work"),
            judge_model_args=None,
        )
    except EvalScopeDirectError as exc:
        assert "sandbox_required:mbpp_plus" in str(exc)
    else:
        raise AssertionError("expected sandbox_required error for mbpp_plus")


def test_intelligence_executor_does_not_enable_sandbox_for_non_code_dataset(tmp_path):
    executor = EvalScopeIntelligenceExecutor(
        EvalScopeConfig(
            outputs_dir=str(tmp_path / "outputs"),
            sandbox_enabled=True,
            sandbox_manager_config={"base_url": "http://sandbox.local:1234"},
        )
    )

    data = executor._task_config_data(
        model="demo",
        api_url="http://model/v1/chat/completions",
        api_key="dummy",
        dataset="gsm8k",
        local_paths={},
        limit=1,
        eval_batch_size=1,
        generation_config=None,
        work_dir=str(tmp_path / "work"),
        judge_model_args=None,
    )

    assert "use_sandbox" not in data
    assert "sandbox_manager_config" not in data


def test_stress_direct_executor_builds_evalscope_arguments(monkeypatch, tmp_path):
    seen = {}

    class FakeArguments:
        def __init__(self, **kwargs):
            seen.update(kwargs)

    def fake_run_perf_benchmark(args):
        return {
            "parallel_1_number_2": {
                "metrics": {"concurrency": 1, "total_requests": 2, "succeed_requests": 2, "failed_requests": 0}
            }
        }

    perf_arguments = types.ModuleType("evalscope.perf.arguments")
    perf_arguments.Arguments = FakeArguments
    perf_main = types.ModuleType("evalscope.perf.main")
    perf_main.run_perf_benchmark = fake_run_perf_benchmark
    monkeypatch.setitem(sys.modules, "evalscope.perf.arguments", perf_arguments)
    monkeypatch.setitem(sys.modules, "evalscope.perf.main", perf_main)

    executor = EvalScopeStressExecutor(EvalScopeConfig(outputs_dir=str(tmp_path / "outputs")))
    result = executor.run(
        task_id="stress-task",
        payload=StressRemoteSubmitPayload(
            model="demo",
            url="http://model/v1/chat/completions",
            api_key="dummy-secret-key",
            api="openai",
            parallel=[1],
            number=[2],
        ),
    )

    assert seen["outputs_dir"].endswith("stress-task")
    assert seen["enable_progress_tracker"] is True
    assert seen["api_key"] == "dummy-secret-key"
    assert result["task_id"] == "stress-task"
    assert result["status"] == "completed"
