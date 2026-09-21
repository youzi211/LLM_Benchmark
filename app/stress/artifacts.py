from __future__ import annotations

import mimetypes
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any


def resolve_task_artifact(output_dir: Path, artifact_path: str) -> Path:
    """Resolve an existing task artifact while preventing traversal and symlink escape."""
    relative = PurePosixPath(str(artifact_path).replace("\\", "/"))
    if relative.is_absolute() or Path(artifact_path).is_absolute():
        raise ValueError("artifact path must be relative")
    root = output_dir.resolve(strict=True)
    candidate = (root / Path(*relative.parts)).resolve(strict=True)
    if not candidate.is_relative_to(root):
        raise ValueError("artifact path is outside task output directory")
    if not candidate.is_file():
        raise FileNotFoundError(artifact_path)
    return candidate


def list_task_artifacts(output_dir: Path) -> list[dict[str, Any]]:
    root = output_dir.resolve(strict=True)
    artifacts: list[dict[str, Any]] = []
    for entry in root.rglob("*"):
        try:
            resolved = entry.resolve(strict=True)
        except OSError:
            continue
        if not resolved.is_file() or not resolved.is_relative_to(root):
            continue
        stat = resolved.stat()
        relative = entry.relative_to(root).as_posix()
        artifacts.append({
            "name": entry.name,
            "path": relative,
            "size_bytes": stat.st_size,
            "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            "content_type": mimetypes.guess_type(entry.name)[0] or "application/octet-stream",
        })
    return sorted(artifacts, key=lambda item: item["path"])
