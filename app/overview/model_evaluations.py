"""Read models over existing task archives; no second raw-result store."""
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.core.snapshots import public_data
from app.intelligence.report_summary import primary_summary
from app.storage.model_store import ModelStore
from app.storage.task_store import TaskStore
from app.storage.intelligence_task_store import IntelligenceTaskStore
from app.storage.stress_task_store import StressTaskStore
from app.suites.store import SuiteRunStore

Lane = Literal["basic", "intelligence", "stress"]
LANES: tuple[Lane, ...] = ("basic", "intelligence", "stress")


class ComparisonRequest(BaseModel):
    model_ids: list[str] = Field(min_length=2, max_length=4)
    task_overrides: dict[str, dict[Lane, str]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_ids(self):
        if len(set(self.model_ids)) != len(self.model_ids):
            raise ValueError("model_ids must be distinct")
        if set(self.task_overrides) - set(self.model_ids):
            raise ValueError("task_overrides must reference selected models")
        return self


def task_stores(root: Path | None = None):
    return {"basic": TaskStore(root / "tasks" if root else None),
            "intelligence": IntelligenceTaskStore(root / "intelligence_tasks" if root else None),
            "stress": StressTaskStore(root / "stress_tasks" if root else None)}


def has_history(model_id: str, root: Path | None = None) -> bool:
    return (any(task.model_id == model_id for store in task_stores(root).values() for task in store.iter_tasks())
            or any(s.model_id == model_id for s in SuiteRunStore(root / "suite_runs" if root else None).list(limit=None)))


def _timestamp(task, finished=False):
    fields = ("completed_at", "finished_at") if finished else ("created_at", "started_at")
    value = next((getattr(task, key) for key in fields if key in task.model_fields_set and getattr(task, key, None)), None)
    # Legacy engine timestamps used local wall time; preserve the archive as written.
    return value.astimezone(timezone.utc) if value else datetime.min.replace(tzinfo=timezone.utc)


def _known_execution_time(task):
    value = next((getattr(task, key) for key in ("created_at", "started_at")
                  if key in task.model_fields_set and getattr(task, key, None)), None)
    return value.astimezone(timezone.utc) if value and value.tzinfo is not None else None


def evidence(lane: str, task) -> dict[str, Any]:
    snapshot = getattr(task, "execution_snapshot", None)
    rows: list[dict[str, Any]] = []
    complete: bool | None = None
    load_mode = None
    completed_at = getattr(task, "completed_at", None) or getattr(task, "finished_at", None)
    if lane == "basic":
        rows = [{"metric_id": r.metric_id, "status": r.status, "summary": r.summary} for r in task.results]
        complete = set(task.metric_ids).issubset({r.metric_id for r in task.results})
    elif lane == "stress":
        from app.stress.runner import StressRunner
        task = StressRunner.normalize_for_list(task)
        normalized = task.normalized_result
        if normalized:
            rows = [r.model_dump(mode="json", exclude={"raw"}) for r in normalized.runs]
        config = task.request_config or {}
        load_mode = ("open" if config["open_loop"] else "closed") if isinstance(config.get("open_loop"), bool) else "unknown"
        expected = config.get("rate") if config.get("open_loop") else config.get("parallel")
        count = len(expected) if isinstance(expected, list) else 1
        complete = bool(rows) and len(rows) == count
    else:
        raw = task.raw_result or {}
        for row in raw.get("results") or []:
            if isinstance(row, dict) and isinstance(row.get("report"), dict):
                rows.append({"dataset": row.get("dataset") or row.get("dataset_name"), **primary_summary(row["report"])})
        if not rows and task.normalized_result:
            rows = [r.model_dump(mode="json") for r in task.normalized_result.dataset_results]
        complete = (set(task.datasets).issubset({r.get("dataset") for r in rows})
                    and all(r.get("score") is not None and r.get("complete") is not False for r in rows)
                    and not raw.get("errors"))
    valid = bool(rows)
    if lane == "intelligence":
        valid = any(r.get("score") is not None for r in rows)
    return public_data({"task_id": task.task_id, "model_id": task.model_id, "lane": lane,
                        "status": task.status, "cancel_requested_at": getattr(task, "cancel_requested_at", None),
                        "created_at": _timestamp(task).isoformat() if _timestamp(task) != datetime.min.replace(tzinfo=timezone.utc) else None,
                        "completed_at": completed_at,
                        "timestamp_timezone_known": completed_at is not None and completed_at.tzinfo is not None,
                        "complete": complete, "valid": valid, "metrics": rows, "load_mode": load_mode,
                        "snapshot": snapshot, "conditions_known": snapshot is not None,
                        "report_url": (f"/api/reports/{task.task_id}" if lane == "basic" else f"/api/{lane}/reports/{task.task_id}") if task.report_path else None,
                        "task_url": f"/api/{'tasks' if lane == 'basic' else lane + '/tasks'}/{task.task_id}"})


class ModelEvaluations:
    def __init__(self):
        self.models = {m.id: m for m in ModelStore().list(include_archived=True)}
        self.tasks: dict[str, dict[str, list]] = {}
        for lane, store in task_stores().items():
            for task in store.iter_tasks():
                self.tasks.setdefault(task.model_id, {key: [] for key in LANES})[lane].append(task)
        for suite in SuiteRunStore().list(limit=None):
            self.tasks.setdefault(suite.model_id, {key: [] for key in LANES})

    def detail(self, model_id: str) -> dict[str, Any]:
        model = self.models.get(model_id)
        groups = self.tasks.get(model_id)
        if model is None and groups is None:
            raise KeyError(model_id)
        lanes = {}
        for lane in LANES:
            tasks = (groups or {}).get(lane, [])
            ordered = sorted(tasks, key=lambda t: (_timestamp(t, True), t.task_id), reverse=True)
            latest = max(tasks, key=lambda t: (_timestamp(t), t.task_id), default=None)
            success = partial = None
            for task in ordered:
                if task.status != "completed":
                    continue
                item = evidence(lane, task)
                if not item["valid"]:
                    continue
                if item["complete"]:
                    success = item
                    break
                if partial is None:
                    partial = item
            lanes[lane] = {"latest_success": success, "latest_attempt": evidence(lane, latest) if latest else None,
                           "partial_result": partial if success is None else None, "task_count": len(tasks)}
        execution_times = [value for tasks in (groups or {}).values() for task in tasks
                           if (value := _known_execution_time(task)) is not None]
        return {"model_id": model_id, "name": model.name if model else model_id,
                "upstream_model": model.model if model else None, "protocol": model.protocol if model else None,
                "enabled": model.enabled if model else False, "archived": bool(model.archived_at) if model else True,
                "historical_only": model is None, "lanes": lanes,
                "last_execution_at": max(execution_times).isoformat() if execution_times else None,
                "coverage": sum(bool(v["latest_success"]) for v in lanes.values())}

    def history(self, model_id: str, lane: Lane | None, page: int, page_size: int):
        self.detail(model_id)
        items = [(key, task) for key, tasks in self.tasks.get(model_id, {}).items() if lane is None or key == lane for task in tasks]
        items.sort(key=lambda item: (_timestamp(item[1]), item[1].task_id), reverse=True)
        return {"total": len(items), "items": [evidence(key, t) for key, t in items[(page - 1) * page_size:page * page_size]]}

    def compare(self, request: ComparisonRequest):
        models = [self.detail(id) for id in request.model_ids]
        for model in models:
            for lane, task_id in request.task_overrides.get(model["model_id"], {}).items():
                task = next((t for t in self.tasks.get(model["model_id"], {}).get(lane, []) if t.task_id == task_id), None)
                if task is None or task.status not in {"completed", "failed", "error", "interrupted"}:
                    raise ValueError("任务不存在、归属不符或尚未结束")
                model["lanes"][lane]["selected"] = evidence(lane, task)
            for lane in LANES:
                model["lanes"][lane].setdefault("selected", model["lanes"][lane]["latest_success"] or model["lanes"][lane]["partial_result"])
        comparability = {}
        for lane in LANES:
            selected = [m["lanes"][lane]["selected"] for m in models]
            snapshots = [s.get("snapshot") if s else None for s in selected]
            if not all(snapshots):
                comparability[lane] = {"status": "unknown", "reasons": ["缺少结果或历史执行配置"]}
                continue
            keys = ("conditions", "evalscope_version")
            differences = [key for key in keys if any(s.get(key) != snapshots[0].get(key) for s in snapshots[1:])]
            for key in ("protocol", "timeout_seconds"):
                if any(s.get("model", {}).get(key) != snapshots[0].get("model", {}).get(key) for s in snapshots[1:]):
                    differences.append(key)
            unknown_version = lane != "basic" and any(s.get("evalscope_version") is None for s in snapshots)
            unknown_conditions = any(not isinstance(s.get("conditions"), dict) or any(s.get("model", {}).get(key) is None for key in ("protocol", "timeout_seconds")) for s in snapshots)
            if lane == "intelligence":
                unknown_version = unknown_version or any(not s.get("conditions", {}).get("benchmark_versions") or any(v is None for v in s["conditions"]["benchmark_versions"].values()) for s in snapshots)
            comparability[lane] = {"status": "different" if differences else "unknown" if unknown_version or unknown_conditions else "equal",
                                    "reasons": differences or (["执行条件或框架版本未知"] if unknown_version or unknown_conditions else [])}
        return {"models": models, "comparability": comparability}
