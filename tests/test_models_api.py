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
