import pytest
from pathlib import Path

from fastapi.testclient import TestClient


def test_model_store_create_get_update_delete(tmp_path):
    from app.core.models import ModelConfigCreate, ModelConfigUpdate
    from app.storage.model_store import ModelStore

    store = ModelStore(tmp_path / "models.json")
    created = store.create(ModelConfigCreate(
        id="m1",
        name="M1",
        protocol="chat_completions",
        base_url="http://upstream/v1/",
        api_key="sk-secret-123456",
        model="model-a",
    ))
    assert created.base_url == "http://upstream/v1"
    assert store.get("m1").api_key == "sk-secret-123456"

    updated = store.update("m1", ModelConfigUpdate(enabled=False, timeout_seconds=30))
    assert updated.enabled is False
    assert updated.timeout_seconds == 30
    assert store.delete("m1") is True
    assert store.get("m1") is None


def test_models_api_masks_key_but_storage_keeps_plaintext(temp_data_dirs):
    from app.main import app

    data_dir, _ = temp_data_dirs
    client = TestClient(app)
    body = {
        "id": "demo-chat",
        "name": "Demo Chat",
        "protocol": "chat_completions",
        "base_url": "http://127.0.0.1:9001/v1/",
        "api_key": "sk-demo-secret",
        "model": "demo-model",
        "declared_context_tokens": 8192,
        "declared_max_output_tokens": 1024,
        "concurrency_levels": [1, 2],
    }

    created = client.post("/api/models", json=body)
    assert created.status_code == 200, created.text
    assert created.json()["api_key"] == "sk-d...cret"
    assert created.json()["base_url"] == "http://127.0.0.1:9001/v1"

    got = client.get("/api/models/demo-chat")
    assert got.status_code == 200
    assert got.json()["api_key"] == "sk-d...cret"

    stored = Path(data_dir / "models.json").read_text(encoding="utf-8")
    assert "sk-demo-secret" in stored

    deleted = client.delete("/api/models/demo-chat")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert client.get("/api/models/demo-chat").status_code == 404


def test_model_store_reads_and_preserves_analysis_model_id(tmp_path):
    from app.core.models import ModelConfigCreate
    from app.storage.model_store import ModelStore

    store = ModelStore(tmp_path / "models.json")
    store.create(ModelConfigCreate(
        id="report-analyzer",
        name="报告分析模型",
        protocol="chat_completions",
        base_url="http://analysis.local/v1",
        api_key="test-analysis-key",
        model="analysis-model",
    ))
    store.set_analysis_model_id("report-analyzer")

    reloaded = ModelStore(tmp_path / "models.json")
    assert reloaded.get_analysis_model_id() == "report-analyzer"
    assert reloaded.get("report-analyzer").model == "analysis-model"


def test_model_store_legacy_list_form_has_no_analysis_model_id(tmp_path):
    import json
    from app.storage.model_store import ModelStore

    path = tmp_path / "models.json"
    path.write_text(json.dumps([{
        "id": "legacy-model",
        "name": "Legacy Model",
        "protocol": "chat_completions",
        "base_url": "http://legacy.local/v1",
        "api_key": "test-legacy-key",
        "model": "legacy-upstream",
        "timeout_seconds": 60,
        "enabled": True,
        "declared_context_tokens": None,
        "declared_max_output_tokens": None,
        "concurrency_levels": [1, 5, 10, 20],
    }]), encoding="utf-8")

    store = ModelStore(path)
    assert store.get_analysis_model_id() is None
    assert store.get("legacy-model").model == "legacy-upstream"


def test_model_store_rejects_missing_analysis_model_id(tmp_path):
    from app.core.models import ModelConfigCreate
    from app.storage.model_store import ModelStore

    store = ModelStore(tmp_path / "models.json")
    store.create(ModelConfigCreate(
        id="existing",
        name="Existing",
        protocol="chat_completions",
        base_url="http://existing.local/v1",
        api_key="test-existing-key",
        model="existing-model",
    ))

    with pytest.raises(KeyError, match="model_not_found:missing"):
        store.set_analysis_model_id("missing")

    assert store.get_analysis_model_id() is None
    raw = tmp_path / "models.json"
    assert raw.exists() is False or "analysis_model_id" not in raw.read_text(encoding="utf-8")


def test_model_store_clears_analysis_model_id_on_delete(tmp_path):
    from app.core.models import ModelConfigCreate
    from app.storage.model_store import ModelStore

    store = ModelStore(tmp_path / "models.json")
    store.create(ModelConfigCreate(
        id="report-analyzer",
        name="报告分析模型",
        protocol="chat_completions",
        base_url="http://analysis.local/v1",
        api_key="test-analysis-key",
        model="analysis-model",
    ))
    store.create(ModelConfigCreate(
        id="other",
        name="Other",
        protocol="chat_completions",
        base_url="http://other.local/v1",
        api_key="test-other-key",
        model="other-model",
    ))
    store.set_analysis_model_id("report-analyzer")
    assert store.delete("report-analyzer") is True

    assert store.get_analysis_model_id() is None
    assert store.get("report-analyzer") is None
    assert store.get("other") is not None

