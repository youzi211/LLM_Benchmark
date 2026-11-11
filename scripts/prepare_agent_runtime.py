"""Prepare pinned Linux CLI tools outside benchmark images (run on the Docker host)."""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
from pathlib import Path

NODE = "24.11.0"
OPENCODE = "1.19.5"
DSH = "0.1.5-rc.3"


def flatten_symlinks(root: Path) -> None:
    """Replace symlinks with shims; ms_enclave's tar_directory skips them.

    A hardlink would not do: Node resolves relative imports from the entry
    script's argv path, so ``dsh`` linked into ``tools/bin`` breaks. The shim
    hands Node an absolute path.
    """
    for link in [path for path in root.rglob("*") if path.is_symlink()]:
        target = os.path.relpath(link.resolve(), link.parent)
        link.unlink()
        link.write_text(f'#!/bin/sh\nexec "$(cd "$(dirname "$0")" && pwd)/{target}" "$@"\n')
        link.chmod(0o755)


def prepare(target: Path, registry: str) -> None:
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise SystemExit("This bundle targets Linux x86_64 benchmark containers")
    target = target.resolve()
    if target.exists():
        raise SystemExit(f"Refusing to replace {target}; choose an empty versioned directory")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent, prefix=".agent-runtime-") as tmp:
        staging = Path(tmp)
        archive = staging / "node.tar.xz"
        urllib.request.urlretrieve(f"https://nodejs.org/dist/v{NODE}/node-v{NODE}-linux-x64.tar.xz", archive)
        with tarfile.open(archive) as tar:
            tar.extractall(staging, filter="data")
        (staging / f"node-v{NODE}-linux-x64").rename(staging / "node")
        archive.unlink()
        env = {**os.environ, "PATH": f"{staging / 'node/bin'}:{os.environ.get('PATH', '')}"}
        subprocess.run([
            str(staging / "node/bin/npm"), "install", "--global", "--prefix", str(staging / "tools"),
            "--registry", registry, "--no-audit", "--no-fund",
            f"opencode-ai@{OPENCODE}", f"@deepseek-ai/dsh@{DSH}",
        ], env=env, check=True)
        flatten_symlinks(staging)
        env["PATH"] = f"{staging / 'tools/bin'}:{env['PATH']}"
        for command in (["node", "--version"], ["opencode", "--version"], ["dsh", "--help"]):
            subprocess.run(command, env=env, check=True, stdout=subprocess.DEVNULL)
        (staging / "manifest.json").write_text(json.dumps({
            "platform": "linux-x86_64", "node_version": NODE,
            "opencode_version": OPENCODE, "deepseek_harness_version": DSH,
        }, indent=2) + "\n")
        shutil.move(str(staging), target)
    print(f"Agent runtime ready: {target}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, default=Path("data/agent_runtime"))
    parser.add_argument("--registry", default="https://registry.npmmirror.com")
    args = parser.parse_args()
    prepare(args.target, args.registry)
