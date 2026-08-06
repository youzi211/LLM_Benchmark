from app.intelligence.schemas import IntelligenceTask
from app.storage.intelligence_task_store import IntelligenceTaskStore


def test_intelligence_task_store_saves_and_loads(tmp_path):
    store = IntelligenceTaskStore(tmp_path)
    task = IntelligenceTask(task_id="intel_task_20260806120000_aaaaaaaa", model_id="m1", evalscope_base_url="http://e")

    store.save(task)

    loaded = store.get(task.task_id)
    assert loaded is not None
    assert loaded.task_id == task.task_id
    assert loaded.model_id == "m1"


def test_intelligence_task_store_lists_newest_first_and_skips_bad_json(tmp_path):
    store = IntelligenceTaskStore(tmp_path)
    old = IntelligenceTask(task_id="intel_task_20260806110000_aaaaaaaa", model_id="old", evalscope_base_url="http://e")
    new = IntelligenceTask(task_id="intel_task_20260806120000_bbbbbbbb", model_id="new", evalscope_base_url="http://e")
    store.save(old)
    store.save(new)
    (tmp_path / "intel_task_bad.json").write_text("not json", encoding="utf-8")

    tasks = store.list()

    assert [item.model_id for item in tasks] == ["new", "old"]
    assert store.get("missing") is None
