import json
import sys
import types

from app.intelligence.evalscope_direct import (
    EvalScopeDirectError,
    EvalScopeIntelligenceExecutor,
    dataset_metadata,
    judge_config_status,
    summarize_evalscope_task_progress,
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


def test_summarize_evalscope_task_progress_reads_dataset_progress_files(tmp_path):
    root = tmp_path / "outputs" / "intelligence" / "intel_task_1"
    first = root / "humaneval" / "20260828_120000"
    second = root / "live_code_bench" / "20260828_120010"
    first.mkdir(parents=True)
    second.mkdir(parents=True)
    (first / "progress.json").write_text(
        json.dumps({"status": "completed", "pipeline": "eval", "total_count": 10, "processed_count": 10, "percent": 100}),
        encoding="utf-8",
    )
    (second / "progress.json").write_text(
        json.dumps({"status": "running", "pipeline": "eval", "total_count": 200, "processed_count": 50, "percent": 25}),
        encoding="utf-8",
    )

    progress = summarize_evalscope_task_progress(root, ["humaneval", "live_code_bench", "gsm8k"])

    assert progress["current_dataset"] == "live_code_bench"
    assert progress["dataset_index"] == 2
    assert progress["dataset_total"] == 3
    assert progress["processed_count"] == 50
    assert progress["total_count"] == 200
    assert progress["percent"] == 25.0
    assert progress["overall_percent"] == 41.67
    assert "live_code_bench 50/200" in progress["message"]


def test_dataset_metadata_includes_local_subsets_and_descriptions(tmp_path):
    datasets_dir = tmp_path / "datasets"
    (datasets_dir / "bbh" / "boolean_expressions").mkdir(parents=True)
    (datasets_dir / "bbh" / "date_understanding").mkdir(parents=True)
    (datasets_dir / "live_code_bench" / "release_latest").mkdir(parents=True)
    (datasets_dir / "live_code_bench" / "release_v6").mkdir(parents=True)

    data = dataset_metadata(EvalScopeConfig(datasets_dir=str(datasets_dir)))

    bbh = data["datasets"]["bbh"]
    assert bbh["available_local"] is True
    assert bbh["description"] == "Big-Bench Hard 复杂推理"
    assert bbh["subset_count"] == 2
    assert bbh["subsets"] == ["boolean_expressions", "date_understanding"]

    lcb = data["datasets"]["live_code_bench"]
    assert lcb["available_local"] is True
    assert lcb["configured_subset_list"] == ["release_latest"]
    assert lcb["subsets"] == ["release_latest", "release_v6"]


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

    assert data["sandbox"] == {
        "enabled": True,
        "engine": "docker",
        "manager_config": {"base_url": "http://sandbox.local:1234"},
    }
    assert "use_sandbox" not in data
    assert "sandbox_type" not in data
    assert "sandbox_manager_config" not in data


def test_intelligence_executor_defaults_live_code_bench_to_single_subset(tmp_path):
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
        dataset="live_code_bench",
        local_paths={"live_code_bench": str(tmp_path / "datasets" / "live_code_bench")},
        limit=200,
        eval_batch_size=5,
        generation_config=None,
        work_dir=str(tmp_path / "work"),
        judge_model_args=None,
    )

    assert data["limit"] == 200
    assert data["dataset_args"]["live_code_bench"]["subset_list"] == ["release_latest"]
    assert data["dataset_args"]["live_code_bench"]["local_path"].endswith("live_code_bench")


def test_intelligence_executor_allows_configured_dataset_args_to_override_builtin_subset(tmp_path):
    executor = EvalScopeIntelligenceExecutor(
        EvalScopeConfig(
            outputs_dir=str(tmp_path / "outputs"),
            sandbox_enabled=True,
            dataset_args={"live_code_bench": {"subset_list": ["release_v6"], "extra_params": {"debug": True}}},
        )
    )

    data = executor._task_config_data(
        model="demo",
        api_url="http://model/v1/chat/completions",
        api_key="dummy",
        dataset="live_code_bench",
        local_paths={},
        limit=200,
        eval_batch_size=5,
        generation_config=None,
        work_dir=str(tmp_path / "work"),
        judge_model_args=None,
    )

    assert data["dataset_args"]["live_code_bench"]["subset_list"] == ["release_v6"]
    assert data["dataset_args"]["live_code_bench"]["extra_params"] == {"debug": True}


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

    assert "sandbox" not in data
    assert "use_sandbox" not in data
    assert "sandbox_type" not in data
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
