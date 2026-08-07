import json
from pathlib import Path

from app.intelligence.config_store import EvalScopeConfigStore
from app.intelligence.schemas import EvalScopeConfig


def test_evalscope_config_store_loads_defaults(tmp_path):
    config = EvalScopeConfigStore(tmp_path / "missing.json").load()

    assert config.datasets_dir is None
    assert config.outputs_dir is None
    assert config.judge_model_config_id is None
    assert config.ignore_dataset_errors is True


def test_evalscope_config_store_ignores_legacy_base_url_and_round_trips_compact_override(tmp_path):
    path = tmp_path / "evalscope.json"
    store = EvalScopeConfigStore(path)

    path.write_text('{"base_url":"http://legacy.local/api/v1","outputs_dir":" outputs/evalscope/ "}', encoding="utf-8")

    loaded = store.load()
    assert not hasattr(loaded, "base_url")
    assert loaded.outputs_dir == "outputs/evalscope"

    store.save(EvalScopeConfig(outputs_dir="outputs/custom", judge_model_config_id="judge-model", ignore_dataset_errors=False))
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "outputs_dir": "outputs/custom",
        "judge_model_config_id": "judge-model",
        "ignore_dataset_errors": False,
    }


def test_evalscope_config_store_round_trips_remote_sandbox_override(tmp_path):
    path = tmp_path / "evalscope.json"
    store = EvalScopeConfigStore(path)

    path.write_text(
        '{"sandbox_enabled":true,"sandbox_type":" docker ","sandbox_manager_config":{"base_url":"http://sandbox.local:1234"}}',
        encoding="utf-8",
    )

    loaded = store.load()
    assert loaded.sandbox_enabled is True
    assert loaded.sandbox_type == "docker"
    assert loaded.sandbox_manager_config == {"base_url": "http://sandbox.local:1234"}

    store.save(loaded)
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "sandbox_enabled": True,
        "sandbox_manager_config": {"base_url": "http://sandbox.local:1234"},
    }
