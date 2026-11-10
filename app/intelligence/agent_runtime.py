from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Coroutine, TypeVar
from urllib.parse import urlsplit, urlunsplit

T = TypeVar("T")


class AgentCancelledError(RuntimeError):
    pass


def runtime_bundle(root: Path, framework: str) -> dict[str, Any]:
    try:
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        version_key = "opencode_version" if framework == "opencode" else "deepseek_harness_version"
        cli = "opencode" if framework == "opencode" else "dsh"
        if (not manifest.get(version_key) or not (root / "node" / "bin" / "node").is_file()
                or not (root / "tools" / "bin" / cli).is_file()):
            raise ValueError("incomplete bundle")
        return manifest
    except (OSError, ValueError, TypeError) as exc:
        raise ValueError(f"agent_runtime_missing:{framework}; prepare {root}/manifest.json and portable CLI tools") from exc


async def cancellable(operation: Coroutine[Any, Any, T], marker: Path) -> T:
    task = asyncio.create_task(operation)
    try:
        while not task.done():
            if marker.exists():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                raise AgentCancelledError("Agent evaluation cancelled; operation cleanup finished")
            await asyncio.wait({task}, timeout=0.2)
        return await task
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


class PreparedEnvironment:
    """Keep the benchmark's environment and add the prebuilt CLI tools to PATH."""

    def __init__(self, environment: Any):
        self.environment = environment

    def __getattr__(self, name: str) -> Any:
        return getattr(self.environment, name)

    async def exec(self, cmd: list[str], **kwargs: Any) -> Any:
        if cmd and cmd[0] == "opencode":
            # OpenCode 1.19 uses --auto for the permission flag emitted by EvalScope 1.14.
            cmd = ["--auto" if arg == "--dangerously-skip-permissions" else arg for arg in cmd]
        # Preserve the task image's PATH and environment; only prepend the portable tools.
        wrapped = ["bash", "-c", 'export PATH="/opt/llm-benchmark-agent/node/bin:/opt/llm-benchmark-agent/tools/bin:$PATH"; exec "$@"', "--", *cmd]
        return await self.environment.exec(wrapped, **kwargs)


class PreparedRunnerMixin:
    def __init__(self, *, runtime_dir: str, cancel_file: str, bridge_host: str = "", **kwargs: Any):
        super().__init__(auto_install=False, **kwargs)
        self.runtime_dir = Path(runtime_dir)
        self.cancel_file = Path(cancel_file)
        self.bridge_host = bridge_host

    async def setup(self, env: Any) -> None:
        runtime_bundle(self.runtime_dir, self.framework)

        async def prepare() -> None:
            await env.put_dir(self.runtime_dir, "/opt/llm-benchmark-agent")
            await super(PreparedRunnerMixin, self).setup(PreparedEnvironment(env))

        await cancellable(prepare(), self.cancel_file)

    async def run(self, task: Any, env: Any, bridge: Any) -> Any:
        if self.bridge_host:
            parts = urlsplit(bridge.base_url)
            host = f"[{self.bridge_host}]" if ":" in self.bridge_host else self.bridge_host
            bridge = bridge.model_copy(update={"base_url": urlunsplit((parts.scheme, f"{host}:{parts.port}", parts.path, "", ""))})
        return await cancellable(super().run(task, PreparedEnvironment(env), bridge), self.cancel_file)


def register_project_runners() -> None:
    from evalscope.api.registry import RUNNER_REGISTRY, register_runner
    from evalscope.agent.external.runners.opencode import OpenCodeRunner
    from evalscope.agent.external.runners.deepseek_harness import DeepSeekHarnessRunner

    for name, base in (("opencode", OpenCodeRunner), ("deepseek-harness", DeepSeekHarnessRunner)):
        alias = f"benchmark-{name}"
        if alias not in RUNNER_REGISTRY:
            register_runner(alias)(type(f"Prepared{base.__name__}", (PreparedRunnerMixin, base), {}))


def runtime_root(config: Any) -> Path:
    return Path(config.agent_runtime_dir or os.getenv("LLM_BENCHMARK_AGENT_RUNTIME_DIR") or "data/agent_runtime").resolve()


def cancel_marker(config: Any, task_id: str) -> Path:
    from app.intelligence.evalscope_direct import outputs_root

    return outputs_root(config).resolve() / "intelligence" / task_id / "cancel-requested"


def bridge_host(config: Any) -> str:
    host = config.agent_bridge_host or os.getenv("LLM_BENCHMARK_AGENT_BRIDGE_HOST")
    if host:
        return host
    import subprocess

    # Docker's host bridge is reachable from both normal and egress-controlled trials.
    result = subprocess.run(["docker", "network", "inspect", "bridge", "--format", "{{(index .IPAM.Config 0).Gateway}}"],
                            capture_output=True, text=True, check=True, timeout=10)
    import ipaddress

    return str(ipaddress.ip_address(result.stdout.strip()))
