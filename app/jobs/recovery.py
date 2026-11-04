"""Single-process startup reconciliation; never replay interrupted work."""
from app.core.models import utc_now
from app.jobs.store import JobStore
from app.storage.task_store import TaskStore
from app.storage.intelligence_task_store import IntelligenceTaskStore
from app.storage.stress_task_store import StressTaskStore
from app.suites.store import SuiteRunStore, SuiteScheduleStore, compute_following_run_at


def reconcile_startup() -> None:
    now = utc_now()
    stores = [JobStore(), TaskStore(), IntelligenceTaskStore(), StressTaskStore(), SuiteRunStore()]
    for store in stores:
        for record in store.list(limit=None):
            if record.status not in {"queued", "pending", "running"}:
                continue
            record.status = "interrupted"
            if hasattr(record, "error"):
                record.error = {"type": "ProcessRestart", "message": "服务重启，原执行已中断；未自动重跑"}
            if hasattr(record, "completed_at"):
                record.completed_at = now
            if hasattr(record, "finished_at"):
                record.finished_at = now
            store.save(record)
    schedules = SuiteScheduleStore()
    for schedule in schedules.list(limit=None):
        if not schedule.enabled or schedule.next_run_at >= now:
            continue
        if schedule.run_once:
            schedule.enabled = False
        else:
            schedule.next_run_at = compute_following_run_at(schedule, now=now)
        schedules.save(schedule)
