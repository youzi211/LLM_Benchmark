from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.core.models import TaskResult
from app.main import app


def test_async_task_submission_persists_queued_task_with_job_id(monkeypatch, temp_data_dirs):
    from app.api import routes_tasks
    from app.jobs.schemas import JobRecord
    from app.storage.task_store import TaskStore

    captured: dict = {}

    class FakeExecutor:
        def submit_async(self, *, job_type, target_id, payload, func, job_id):
            captured.update(
                job_type=job_type,
                target_id=target_id,
                payload=payload,
                func=func,
            )
            return JobRecord(
                job_id=job_id,
                job_type=job_type,
                target_id=target_id,
                payload=payload,
            )

    monkeypatch.setattr(routes_tasks, "get_job_executor", lambda: FakeExecutor())

    response = TestClient(app).post(
        "/api/tasks/run-async",
        json={"model_id": "demo-model", "plan_id": "gateway_acceptance_v1"},
    )

    assert response.status_code == 202, response.text
    payload = response.json()
    assert payload["job_id"].startswith("job_")
    assert payload["status"] == "queued"

    saved = TaskStore().get(payload["task_id"])
    assert saved is not None
    assert saved.status == "queued"
    assert saved.job_id == payload["job_id"]
    assert captured["target_id"] == payload["task_id"]
    assert captured["job_type"] == "basic"


def test_cancelling_basic_task_marks_task_interrupted(monkeypatch, temp_data_dirs):
    from app.api import routes_tasks
    from app.jobs.schemas import JobRecord
    from app.storage.task_store import TaskStore

    store = TaskStore()
    task = TaskResult(
        task_id="task_running",
        job_id="job_running",
        status="running",
        model_id="demo-model",
        plan_id="gateway_acceptance_v1",
        metric_ids=["connectivity"],
        started_at=datetime.now(UTC),
    )
    store.save(task)
    cancelled_ids: list[str] = []

    class FakeExecutor:
        async def cancel(self, job_id):
            cancelled_ids.append(job_id)
            return JobRecord(job_id=job_id, job_type="basic", status="interrupted")

    monkeypatch.setattr(routes_tasks, "get_job_executor", lambda: FakeExecutor())

    response = TestClient(app).post("/api/tasks/task_running/cancel")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "interrupted"
    assert cancelled_ids == ["job_running"]
    assert store.get("task_running").status == "interrupted"
