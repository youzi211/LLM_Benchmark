"""Local Harbor tasks with EvalScope's external runners and per-trial model bridge."""
from __future__ import annotations

import asyncio
import json
import shlex
import time
import uuid
from pathlib import Path
from typing import Any

from harbor.agents.base import BaseAgent

from app.intelligence.agent_runtime import cancellable, register_project_runners


def local_tasks(root: Path) -> Path:
    for candidate in (root / "default", root / "tasks", root):
        if candidate.is_dir() and any(
            (task / "task.toml").is_file() and (task / "instruction.md").is_file()
            and (task / "tests" / "test.sh").is_file()
            for task in candidate.iterdir() if task.is_dir()
        ):
            return candidate
    raise ValueError(f"agent_dataset_invalid: no Harbor tasks in {root}")


class HarborEnvironment:
    name = "harbor"

    def __init__(self, environment: Any):
        self.environment = environment

    async def exec(self, cmd: list[str], *, cwd=None, input=None, timeout=None, env=None):
        from evalscope.api.agent.types import ExecResult

        if input is not None:
            raise ValueError("stdin is not supported by this Harbor bridge")
        started = time.monotonic()
        command = shlex.join(cmd)
        # A client-side Docker exec timeout leaves the child alive; bound the process inside the container.
        if timeout:
            command = shlex.join(["timeout", "-k", "5", str(max(1, int(timeout))), *cmd])
        try:
            result = await self.environment.exec(command=command, cwd=cwd, env=env,
                                                 timeout_sec=timeout + 10 if timeout else None)
        except asyncio.TimeoutError:
            return ExecResult(returncode=124, timed_out=True, duration=time.monotonic() - started)
        return ExecResult(returncode=result.return_code, timed_out=result.return_code in {124, 137}, stdout=result.stdout or "", stderr=result.stderr or "",
                          duration=time.monotonic() - started)

    async def put_dir(self, source_dir, target_dir):
        await self.environment.upload_dir(source_dir=Path(source_dir), target_dir=target_dir)


class BridgeAgent(BaseAgent):
    def __init__(self, *args, framework: str, runtime_dir: str, cancel_file: str,
                 bridge_host: str, timeout: float, capture_patch: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self.framework = framework
        self.bridge_host = bridge_host
        self.timeout = timeout
        self.capture_patch = capture_patch
        self.model = None  # Injected in memory after Trial.create; never serialized into config.json.
        self.trace = None
        self.messages = None
        register_project_runners()
        from evalscope.api.registry import get_runner

        self.runner = get_runner(f"benchmark-{framework}")(
            runtime_dir=runtime_dir, cancel_file=cancel_file, bridge_host=bridge_host,
            model_name=self.model_name or "default",
        )

    @staticmethod
    def name() -> str:
        return "evalscope-external-bridge"

    def version(self) -> str:
        return "1.0.0"

    async def setup(self, environment):
        await self.runner.setup(HarborEnvironment(environment))

    async def run(self, instruction, environment, context):
        from evalscope.agent.external.bridge.server import ModelProxyServer
        from evalscope.agent.external.runners.base import ExternalAgentTask
        from evalscope.agent.external.runners.base import RunnerTimeoutError

        proxy = await ModelProxyServer.get_or_start(host="0.0.0.0")
        async with proxy.trial_session(model=self.model, framework=self.framework) as session:
            try:
                result = await self.runner.run(
                    ExternalAgentTask(instruction=instruction, timeout=self.timeout,
                                      metadata={"sample_id": self.logs_dir.parent.name}),
                    HarborEnvironment(environment), session.endpoint_view(),
                )
                self.logs_dir.mkdir(parents=True, exist_ok=True)
                (self.logs_dir / "stdout.txt").write_text(result.output, encoding="utf-8")
                if not session.recorder.messages():
                    raise RuntimeError("agent_no_model_requests: CLI did not call the selected model")
            except RunnerTimeoutError:
                if not self.capture_patch or not session.recorder.messages():
                    raise
                (self.logs_dir / "agent-timeout.txt").write_text("Agent budget exhausted; grading captured patch in a fresh image.")
            finally:
                self.trace = session.recorder.snapshot()
                self.messages = session.recorder.messages()
                if self.capture_patch:
                    patch = await environment.exec(
                        command="cd /app 2>/dev/null || cd /testbed; git add -A; git diff --cached --binary; git reset >/dev/null",
                        timeout_sec=120,
                    )
                    if patch.return_code != 0:
                        raise RuntimeError("agent_patch_capture_failed")
                    self.logs_dir.mkdir(parents=True, exist_ok=True)
                    (self.logs_dir / "model.patch").write_text(patch.stdout or "", encoding="utf-8")


class PatchReplayAgent(BaseAgent):
    """Apply only the captured diff in a fresh official V2 image, then run its verifier."""

    def __init__(self, *args, patch_path: str, **kwargs):
        super().__init__(*args, **kwargs)
        self.patch_path = Path(patch_path)

    @staticmethod
    def name() -> str:
        return "swe-pro-v2-patch-replay"

    def version(self) -> str:
        return "1.0.0"

    async def setup(self, environment):
        pass

    async def run(self, instruction, environment, context):
        if not self.patch_path.is_file():
            raise RuntimeError("agent_patch_missing")
        if self.patch_path.stat().st_size == 0:
            return
        await environment.upload_file(source_path=self.patch_path, target_path="/tmp/replay.patch")
        result = await environment.exec(
            command="cd /app 2>/dev/null || cd /testbed; git apply --verbose /tmp/replay.patch "
                    "|| git apply --3way /tmp/replay.patch || patch --fuzz=3 -p1 -i /tmp/replay.patch",
            timeout_sec=300,
        )
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        (self.logs_dir / "replay.json").write_text(json.dumps({"apply_rc": result.return_code,
                    "output": ((result.stdout or "") + (result.stderr or ""))[-6000:]}), encoding="utf-8")
        if result.return_code != 0:
            raise RuntimeError("agent_patch_apply_failed")


def _mirrored_image(image: str, mirror: str) -> str:
    if "/" not in image:
        return f"{mirror}/library/{image}"
    if image.startswith(f"{mirror}/"):
        return image
    host, _, path = image.partition("/")
    if host == "docker.io":
        return f"{mirror}/{path}"
    if "." in host or ":" in host or host == "localhost":
        if mirror == "docker.1ms.run" and host == "ghcr.io":
            return f"ghcr.1ms.run/{path}"
        return image
    return f"{mirror}/{image}"


def _rewrite_docker_registry(task, registry: str | None, trial=None) -> None:
    if not registry:
        return
    mirror = registry.strip().rstrip("/")
    if not mirror or "://" in mirror:
        raise ValueError("docker_registry_mirror must be a registry host without a URL scheme")
    environments = [task.config.environment, task.config.verifier.environment]
    environments.extend(step.verifier.environment for step in task.config.steps or [])
    agent_environment = getattr(trial, "agent_environment", None) if trial is not None else None
    if agent_environment is not None:
        environments.append(agent_environment.task_env_config)
    for environment in environments:
        if environment.docker_image:
            environment.docker_image = _mirrored_image(environment.docker_image, mirror)
    compose = getattr(agent_environment, "_env_vars", None) if agent_environment is not None else None
    if compose and compose.prebuilt_image_name:
        compose.prebuilt_image_name = _mirrored_image(compose.prebuilt_image_name, mirror)
    compose_path = getattr(agent_environment, "_environment_docker_compose_path", None)
    if compose_path and compose_path.is_file():
        import yaml

        services = yaml.safe_load(compose_path.read_text()).get("services", {})
        overrides = {name: {"image": _mirrored_image(service["image"], mirror)}
                     for name, service in services.items()
                     if service.get("image") and "$" not in service["image"]}
        if overrides:
            # Harbor appends this overlay after task compose; official task files stay pinned.
            overlay = trial.agent.logs_dir.parent / "registry-mirror-compose.json"
            overlay.parent.mkdir(parents=True, exist_ok=True)
            overlay.write_text(json.dumps({"services": overrides}), encoding="utf-8")
            agent_environment.extra_docker_compose_paths.append(overlay)


async def run_trials(config, model, marker: Path, *, regrade: bool, docker_registry_mirror: str | None = None):
    from harbor.trial.trial import Trial

    config = config.model_copy(deep=True)
    config.trial_name = f"{config.task.path.name}__{uuid.uuid4().hex[:8]}"
    if regrade:
        config.verifier.disable = True
    trial = await Trial.create(config)
    if docker_registry_mirror:
        _rewrite_docker_registry(trial.task, docker_registry_mirror, trial)
    trial.agent.model = model
    result = await cancellable(trial.run(), marker)
    trace = (getattr(trial.agent, "trace", None), getattr(trial.agent, "messages", None))
    if result.exception_info:
        raise RuntimeError(f"agent_trial_failed:{result.exception_info}")
    if regrade:
        replay = config.model_copy(deep=True)
        replay.trial_name += "__regrade"
        replay.verifier.disable = False
        from harbor.models.trial.config import AgentConfig

        replay.agent = AgentConfig(import_path="app.intelligence.harbor_agent:PatchReplayAgent",
            model_name="patch-replay", override_timeout_sec=300,
            kwargs={"patch_path": (config.trials_dir / config.trial_name / "agent" / "model.patch").as_posix()})
        fresh = await Trial.create(replay)
        if docker_registry_mirror:
            _rewrite_docker_registry(fresh.task, docker_registry_mirror, fresh)
        result = await cancellable(fresh.run(), marker)
    return result, trace


def register_harbor_benchmarks() -> None:
    from copy import deepcopy
    from evalscope.api.registry import BENCHMARK_REGISTRY
    from evalscope.benchmarks.terminal_bench.terminal_bench_adapter import TerminalBenchV4Adapter

    class LocalHarborAdapter(TerminalBenchV4Adapter):
        def load(self):
            from harbor.models.job.config import DatasetConfig
            from evalscope.api.dataset import DatasetDict, build_dataset_from_records
            from evalscope.utils.asyncio_runtime import AsyncioLoopRunner

            root = Path(self.benchmark_meta.dataset_id)
            tasks = local_tasks(root)
            names = self.extra_params.get("task_names")
            if names is not None:
                if not isinstance(names, list) or not names:
                    raise ValueError("task_names must be a nonempty list")
                names = [name.rsplit("/", 1)[-1] for name in names]
            configs = AsyncioLoopRunner.run(DatasetConfig(path=tasks, task_names=names).get_task_configs())
            if not configs:
                raise ValueError("agent_dataset_empty_selection")
            datasets = {}
            for subset in self.subset_list:
                selected = configs
                if self.name == "swe_bench_pro_v2" and subset == "hard":
                    ids = set((root / "hard51_ids.txt").read_text().splitlines())
                    selected = [item for item in configs if item.path.name in ids]
                    if not selected:
                        raise ValueError("agent_dataset_empty_selection")
                datasets[subset] = build_dataset_from_records(
                    records=[item.model_dump(mode="json") for item in selected], sample_fields=self.record_to_sample,
                    name=subset, location=str(tasks), limit=self.limit, repeats=self.repeats,
                    shuffle=self.shuffle, seed=42,
                )
            return DatasetDict(datasets), None

        def _on_inference(self, model, sample):
            from evalscope.api.evaluator import InferenceResult
            from evalscope.api.model import ModelOutput
            from evalscope.utils.asyncio_runtime import AsyncioLoopRunner
            from harbor.models.trial.config import AgentConfig, EnvironmentConfig, TrialConfig, TaskConfig, VerifierConfig

            options = self.extra_params["project_agent"]
            is_pro = self.name == "swe_bench_pro_v2"
            kwargs = {k: v for k, v in options.items() if k not in {"timeout", "docker_registry_mirror", "model_name"}}
            config = TrialConfig(
                task=TaskConfig.model_validate(sample.metadata), trials_dir=Path(self.output_dir) / "trials",
                agent=AgentConfig(import_path="app.intelligence.harbor_agent:BridgeAgent", model_name=model.name,
                    override_timeout_sec=options["timeout"] + (135 if is_pro else 15), extra_allowed_hosts=[options["bridge_host"]],
                    kwargs={**kwargs, "timeout": options["timeout"], "capture_patch": is_pro}),
                verifier=VerifierConfig(override_timeout_sec=self.verifier_timeout_sec),
                environment=EnvironmentConfig(type=self.environment_type, **{**self.environment_kwargs, "delete": True}),
                timeout_multiplier=self.timeout_multiplier, agent_timeout_multiplier=self.agent_timeout_multiplier,
                verifier_timeout_multiplier=self.verifier_timeout_multiplier,
            )
            mirror = options.get("docker_registry_mirror") or self.extra_params.get("docker_registry_mirror")
            result, (trace, messages) = AsyncioLoopRunner.run(
                run_trials(config, model, Path(options["cancel_file"]), regrade=is_pro,
                           docker_registry_mirror=mirror))
            payload = result.model_dump(mode="json")
            self._extract_valid_reward(payload)
            sample.metadata["result"] = payload
            return InferenceResult(output=ModelOutput.from_content(model=model.name, content=payload.get("trial_uri", "")),
                                   trace=trace, messages=messages)

    BENCHMARK_REGISTRY["terminal_bench_v4"].data_adapter = LocalHarborAdapter
    BENCHMARK_REGISTRY["terminal_bench_v4"].extra_params["project_agent"] = {
        "type": "dict", "description": "Project external runner configuration", "value": {},
    }
    BENCHMARK_REGISTRY["terminal_bench_v4"].extra_params["docker_registry_mirror"] = {
        "type": "string", "description": "Optional registry prefix used only at runtime for pinned task images", "value": None,
    }
    if "swe_bench_pro_v2" not in BENCHMARK_REGISTRY:
        meta = deepcopy(BENCHMARK_REGISTRY["terminal_bench_v4"])
        meta.name = "swe_bench_pro_v2"
        meta.pretty_name = "SWE-bench Pro V2"
        meta.dataset_id = "data/evalscope_datasets/swe_bench_pro_v2"
        meta.dataset_revision = "66f92766bba642462d4bbe5479e83f91f9211862"
        meta.subset_list = ["default"]
        meta.description = "642 个代码修复任务（hard: 51）；离线 Agent，通过全新官方镜像重放补丁评分。"
        BENCHMARK_REGISTRY[meta.name] = meta
