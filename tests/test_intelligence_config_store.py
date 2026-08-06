from pathlib import Path

from app.intelligence.config_store import EvalScopeConfigStore
from app.intelligence.schemas import EvalScopeConfig


def test_evalscope_config_store_loads_defaults(tmp_path):
    config = EvalScopeConfigStore(tmp_path / "missing.json").load()

    assert config.base_url == "http://localhost:8010/api/v1"
    assert config.poll_interval_seconds == 5
    assert config.default_timeout_seconds == 14400


def test_evalscope_config_store_normalizes_and_round_trips(tmp_path):
    path = tmp_path / "evalscope.json"
    store = EvalScopeConfigStore(path)

    store.save(EvalScopeConfig(base_url="http://evalscope.local/api/v1///", poll_interval_seconds=2))

    loaded = store.load()
    assert loaded.base_url == "http://evalscope.local/api/v1"
    assert loaded.poll_interval_seconds == 2
