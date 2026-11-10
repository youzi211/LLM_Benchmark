from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


def test_local_tasks_require_actual_task_files(tmp_path):
    from app.intelligence.harbor_agent import local_tasks

    with pytest.raises(ValueError, match="agent_dataset_invalid"):
        local_tasks(tmp_path)
    task = tmp_path / "default" / "cpu-task"
    task.mkdir(parents=True)
    (task / "task.toml").write_text("schema_version = '1.4'")
    (task / "instruction.md").write_text("Do work")
    (task / "tests").mkdir()
    (task / "tests" / "test.sh").write_text("exit 0")
    assert local_tasks(tmp_path) == task.parent


def test_project_benchmark_accepts_bridge_options_and_keeps_versions_separate():
    from app.intelligence.harbor_agent import register_harbor_benchmarks
    from evalscope.api.registry import BENCHMARK_REGISTRY

    register_harbor_benchmarks()
    meta = BENCHMARK_REGISTRY["swe_bench_pro_v2"]
    assert meta.dataset_revision == "66f92766bba642462d4bbe5479e83f91f9211862"
    assert meta.data_adapter is not BENCHMARK_REGISTRY["swe_bench_pro"].data_adapter
    assert "project_agent" in meta.extra_params
    assert "docker_registry_mirror" in meta.extra_params


def test_local_harbor_load_preserves_explicit_task_selection_and_limit(tmp_path):
    from app.intelligence.harbor_agent import register_harbor_benchmarks
    from evalscope import TaskConfig
    from evalscope.api.registry import get_benchmark

    for name in ("cpu-task", "other-task"):
        task = tmp_path / "default" / name
        (task / "tests").mkdir(parents=True)
        (task / "environment").mkdir()
        (task / "environment/Dockerfile").write_text("FROM python:3.11-slim")
        (task / "task.toml").write_text("schema_version = '1.4'\n[task]\nname = 'test/" + name + "'\nversion = '1.0.0'\n")
        (task / "instruction.md").write_text("Do work")
        (task / "tests/test.sh").write_text("exit 0")
    register_harbor_benchmarks()
    adapter = get_benchmark("terminal_bench_v4", TaskConfig(model="dummy", datasets=["terminal_bench_v4"],
        limit=1, dataset_args={"terminal_bench_v4": {"local_path": str(tmp_path),
                        "extra_params": {"task_names": ["terminal-bench/cpu-task"], "project_agent": {"framework": "opencode"}}}}))
    test, _ = adapter.load()
    samples = list(next(iter(test.values())))
    assert len(samples) == 1
    assert Path(samples[0].metadata["path"]).name == "cpu-task"


def test_pro_v2_hard_subset_filters_task_ids_and_rejects_empty_selection(tmp_path):
    from app.intelligence.harbor_agent import register_harbor_benchmarks
    from evalscope import TaskConfig
    from evalscope.api.registry import get_benchmark

    root = tmp_path / "swe_bench_pro_v2"
    task_root = root / "tasks"
    for name in ("instance-hard", "instance-easy"):
        task = task_root / name
        (task / "tests").mkdir(parents=True)
        (task / "environment").mkdir()
        (task / "environment/Dockerfile").write_text("FROM python:3.11-slim")
        (task / "task.toml").write_text("schema_version = '1.4'\n[task]\nname = 'test/" + name + "'\nversion = '1.0.0'\n")
        (task / "instruction.md").write_text("Do work")
        (task / "tests/test.sh").write_text("exit 0")
    (root / "hard51_ids.txt").write_text("instance-hard\n")
    register_harbor_benchmarks()

    def load(task_names=None):
        args = {"local_path": str(root), "subset_list": ["hard"]}
        if task_names is not None:
            args["extra_params"] = {"task_names": task_names}
        adapter = get_benchmark("swe_bench_pro_v2", TaskConfig(
            model="dummy", datasets=["swe_bench_pro_v2"], dataset_args={"swe_bench_pro_v2": args}))
        return adapter.load()[0]

    samples = list(next(iter(load().values())))
    assert [Path(sample.metadata["path"]).name for sample in samples] == ["instance-hard"]

    with pytest.raises(ValueError, match="agent_dataset_empty_selection"):
        load(["instance-easy"])


async def test_pro_v2_uses_fresh_replay_verifier(monkeypatch, tmp_path):
    from app.intelligence.harbor_agent import run_trials
    from harbor.models.trial.config import AgentConfig, TaskConfig, TrialConfig, VerifierConfig
    from harbor.trial.trial import Trial

    calls = []
    authoritative = SimpleNamespace(exception_info=None)

    async def create(config):
        calls.append(config)
        return SimpleNamespace(agent=SimpleNamespace(), run=AsyncMock(return_value=authoritative))

    monkeypatch.setattr(Trial, "create", create)
    config = TrialConfig(task=TaskConfig(path=tmp_path / "instance_x"), trials_dir=tmp_path / "trials",
                         agent=AgentConfig(import_path="app.intelligence.harbor_agent:BridgeAgent"),
                         verifier=VerifierConfig())
    result, _ = await run_trials(config, object(), tmp_path / "cancel", regrade=True)
    assert result is authoritative
    assert len(calls) == 2
    assert calls[0].verifier.disable is True
    assert calls[1].verifier.disable is False
    assert calls[1].agent.import_path == "app.intelligence.harbor_agent:PatchReplayAgent"
    assert calls[0].trial_name != calls[1].trial_name
    assert calls[1].agent.kwargs["patch_path"].endswith("/agent/model.patch")


async def test_failed_agent_trial_cannot_be_reported_as_valid_regrade(monkeypatch, tmp_path):
    from app.intelligence.harbor_agent import run_trials
    from harbor.models.trial.config import AgentConfig, TaskConfig, TrialConfig
    from harbor.trial.trial import Trial

    create = AsyncMock(return_value=SimpleNamespace(agent=SimpleNamespace(),
                           run=AsyncMock(return_value=SimpleNamespace(exception_info="image pull failed"))))
    monkeypatch.setattr(Trial, "create", create)
    config = TrialConfig(task=TaskConfig(path=tmp_path / "x"), trials_dir=tmp_path,
                         agent=AgentConfig(import_path="app.intelligence.harbor_agent:BridgeAgent"))
    with pytest.raises(RuntimeError, match="agent_trial_failed"):
        await run_trials(config, object(), tmp_path / "cancel", regrade=True)
    assert create.await_count == 1


def test_docker_registry_rewrite_is_runtime_only():
    from app.intelligence.harbor_agent import _rewrite_docker_registry
    from harbor.models.task.config import EnvironmentConfig, TaskConfig, VerifierConfig

    environment = EnvironmentConfig(docker_image="official/task:tag@sha256:abc")
    compose = SimpleNamespace(prebuilt_image_name=environment.docker_image)
    trial = SimpleNamespace(agent_environment=SimpleNamespace(task_env_config=environment, _env_vars=compose))
    task = SimpleNamespace(config=TaskConfig(
        environment=environment,
        verifier=VerifierConfig(environment=EnvironmentConfig(docker_image="official/verifier:tag@sha256:def")),
    ))
    _rewrite_docker_registry(task, "docker.1ms.run", trial)
    expected = "docker.1ms.run/official/task:tag@sha256:abc"
    assert task.config.environment.docker_image == expected
    assert task.config.verifier.environment.docker_image == "docker.1ms.run/official/verifier:tag@sha256:def"
    assert compose.prebuilt_image_name == expected
