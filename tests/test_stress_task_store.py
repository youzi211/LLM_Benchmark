from datetime import timedelta

from app.core.models import utc_now
from app.storage.stress_task_store import StressTaskStore
from app.stress.schemas import StressTask


def test_stress_task_store_save_get_and_list_order(tmp_path):
    store = StressTaskStore(tmp_path / "stress_tasks")
    older = StressTask(task_id="stress_task_20260806010101_a", model_id="m1", evalscope_base_url="http://eval/api/v1")
    newer = StressTask(task_id="stress_task_20260806010102_b", model_id="m2", evalscope_base_url="http://eval/api/v1")
    older.created_at = utc_now() - timedelta(minutes=1)

    store.save(older)
    store.save(newer)

    assert store.get(older.task_id).model_id == "m1"
    assert [task.task_id for task in store.list()] == [newer.task_id, older.task_id]
    assert store.get("missing") is None
