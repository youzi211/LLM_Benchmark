import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.intelligence.harbor_offline import OfflineDockerEnvironment
from harbor.environments.docker.docker import DockerEnvironment


def environment(tmp_path):
    env = object.__new__(OfflineDockerEnvironment)
    env.dataset = "terminal_bench_v4"
    env.image_cache_root = tmp_path
    env.extra_docker_compose_paths = []
    env._offline_compose_dir = SimpleNamespace(name=str(tmp_path))
    env._offline_sources = {}
    return env


@pytest.mark.parametrize("command", [["pull"], ["build"]])
async def test_offline_harbor_never_calls_pull_or_build(tmp_path, monkeypatch, command):
    run = AsyncMock()
    monkeypatch.setattr(DockerEnvironment, "_run_docker_compose_command", run)
    with pytest.raises(RuntimeError, match="disabled"):
        await environment(tmp_path)._run_docker_compose_command(command)
    run.assert_not_called()


async def test_offline_harbor_missing_cache_stops_before_start(tmp_path, monkeypatch):
    start = AsyncMock()
    monkeypatch.setattr(DockerEnvironment, "start", start)
    with pytest.raises(RuntimeError, match="agent_image_cache_missing"):
        await environment(tmp_path).start(force_build=False)
    start.assert_not_called()


async def test_offline_compose_imports_all_services_and_disables_pull_and_build(tmp_path, monkeypatch):
    from app.intelligence import harbor_offline

    services = {"main": {"image": "task@sha256:abc"}, "verifier": {"image": "verify:one"}, "database": {"image": "postgres:17", "pull_policy": "always"}}
    run = AsyncMock(return_value=SimpleNamespace(stdout=json.dumps({"services": services})))
    monkeypatch.setattr(DockerEnvironment, "_run_docker_compose_command", run)
    imports = []
    def prepare(dataset, images, cache):
        imports.append(images)
        return {image: "offline:" + str(number) for number, image in enumerate(images)}
    monkeypatch.setattr(harbor_offline, "ensure_cached_images", prepare)
    env = environment(tmp_path)
    await env._run_docker_compose_command(["up", "-d"])
    assert imports == [["task@sha256:abc", "verify:one", "postgres:17"]]
    assert run.call_args.args[0] == ["up", "-d", "--pull", "never", "--no-build"]
    overlay = json.loads(Path(env.extra_docker_compose_paths[0]).read_text())
    assert overlay["services"]["database"] == {"image": "offline:2", "pull_policy": "never"}
    assert len(overlay["services"]) == 3
    run.return_value = SimpleNamespace(stdout=json.dumps({"services": {
        name: {"image": "offline:" + str(number)} for number, name in enumerate(services)
    }}))
    await env._run_docker_compose_command(["up", "-d"])
    assert imports[1] == imports[0]
    assert len(env.extra_docker_compose_paths) == 1


async def test_build_only_compose_service_fails_without_starting(tmp_path, monkeypatch):
    run = AsyncMock(return_value=SimpleNamespace(stdout=json.dumps({"services": {"main": {"build": "."}}})))
    monkeypatch.setattr(DockerEnvironment, "_run_docker_compose_command", run)
    with pytest.raises(RuntimeError, match="prepared image"):
        await environment(tmp_path)._run_docker_compose_command(["up", "-d"])
    assert run.await_count == 1
