import asyncio
from pathlib import Path

import pytest

from app.intelligence.agent_runtime import AgentCancelledError, cancellable, runtime_bundle


def test_runtime_bundle_requires_pinned_cli_manifest(tmp_path):
    with pytest.raises(ValueError, match="agent_runtime_missing"):
        runtime_bundle(tmp_path, "opencode")


async def test_prepared_opencode_uses_supported_permission_flag():
    from app.intelligence.agent_runtime import PreparedEnvironment
    from unittest.mock import AsyncMock
    from types import SimpleNamespace

    environment = SimpleNamespace(exec=AsyncMock())
    await PreparedEnvironment(environment).exec(["opencode", "run", "--dangerously-skip-permissions"])
    wrapped = environment.exec.call_args.args[0]
    assert wrapped[:3] == ["bash", "-c", wrapped[2]]
    assert "/opt/llm-benchmark-agent/node/bin" in wrapped[2]
    assert wrapped[4:] == ["opencode", "run", "--auto"]
    assert "env" not in environment.exec.call_args.kwargs


async def test_cancellation_waits_for_running_operation_cleanup(tmp_path):
    marker = tmp_path / "cancel-requested"
    started = asyncio.Event()
    cleaned = asyncio.Event()

    async def operation():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            await asyncio.sleep(0)
            cleaned.set()

    pending = asyncio.create_task(cancellable(operation(), marker))
    await started.wait()
    marker.touch()
    with pytest.raises(AgentCancelledError):
        await asyncio.wait_for(pending, 2)
    assert cleaned.is_set()


async def test_cancellation_does_not_interrupt_another_task(tmp_path):
    marker = tmp_path / "cancel-requested"
    marker.touch()
    with pytest.raises(AgentCancelledError):
        await cancellable(asyncio.sleep(0), marker)
    assert await cancellable(asyncio.sleep(0, result=42), tmp_path / "another-task") == 42


async def test_cancellable_preserves_upstream_error(tmp_path):
    async def operation():
        raise ValueError("infrastructure failed")

    with pytest.raises(ValueError, match="infrastructure failed"):
        await cancellable(operation(), tmp_path / "cancel-requested")


def test_runtime_bundle_has_no_symlinks_since_sandbox_copy_skips_them(tmp_path):
    from scripts.prepare_agent_runtime import flatten_symlinks

    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "tool").write_text("#!/bin/sh\n")
    (tmp_path / "bin" / "alias").symlink_to("tool")
    flatten_symlinks(tmp_path)
    assert not any(path.is_symlink() for path in tmp_path.rglob("*"))
    shim = tmp_path / "bin" / "alias"
    assert 'exec "$(cd "$(dirname "$0")" && pwd)/tool" "$@"' in shim.read_text()
