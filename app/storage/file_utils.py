from __future__ import annotations

import json
import os
import tempfile
from threading import RLock
from pathlib import Path
from typing import Any

_locks: dict[str, RLock] = {}
_locks_guard = RLock()


def file_lock(path: Path) -> RLock:
    with _locks_guard:
        return _locks.setdefault(str(path.resolve()).casefold(), RLock())


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def read_json_file(path: Path, default: Any) -> Any:
    # Windows readers must release their handle before an atomic replacement.
    with file_lock(path):
        if not path.exists():
            return default
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)


def write_json_file_atomic(path: Path, data: Any) -> None:
    ensure_parent(path)
    with file_lock(path):
        fd, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
        temp_path = Path(name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, path)
        finally:
            temp_path.unlink(missing_ok=True)


def save_record(path: Path, record: Any) -> Any:
    """Preserve cancellation and terminal state against stale worker snapshots."""
    with file_lock(path):
        old = read_json_file(path, {})
        terminal = {"completed", "failed", "error", "interrupted", "partial"}
        if old.get("status") in terminal and record.status != old["status"]:
            return type(record).model_validate(old)
        if old.get("cancel_requested_at") and hasattr(record, "cancel_requested_at"):
            record.cancel_requested_at = type(record).model_validate(old).cancel_requested_at
        if old.get("job_id") and hasattr(record, "job_id"):
            record.job_id = old["job_id"]
        from app.utils.json_sanitize import make_json_safe
        write_json_file_atomic(path, make_json_safe(record.model_dump(mode="json")))
        return record
