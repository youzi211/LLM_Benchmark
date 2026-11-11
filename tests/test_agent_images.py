import gzip
import hashlib
import json
from types import SimpleNamespace

import pytest

from app.intelligence import agent_images


def make_cache(root, image="example/task:latest"):
    cache = root / "mini"
    images = cache / "images"
    blobs = images / "blobs/sha256"
    blobs.mkdir(parents=True)

    def blob(value):
        digest = hashlib.sha256(value).hexdigest()
        (blobs / digest).write_bytes(value)
        return {"digest": "sha256:" + digest, "size": len(value)}

    config = blob(b'{"architecture":"amd64","os":"linux"}')
    layer = blob(gzip.compress(b"test layer"))
    layer["mediaType"] = "application/vnd.oci.image.layer.v1.tar+gzip"
    manifest = blob(json.dumps({"config": config, "layers": [layer]}).encode())
    manifest["annotations"] = {"org.opencontainers.image.ref.name": "task-one"}
    (images / "index.json").write_text(json.dumps({"manifests": [manifest]}))
    (cache / "preparation.json").write_text(json.dumps({"tasks": {"one": {
        "image": image, "image_cached": True, "oci_reference": f"oci:{images}:task-one",
    }}}))
    return cache, config["digest"], layer["digest"]


def fake_docker(monkeypatch, root, config_id=None, free=100 * 1024**3):
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        if command[:3] == ["docker", "info", "--format"]:
            output = str(root)
        elif command[:3] == ["docker", "image", "inspect"]:
            if command[-1] == agent_images.SKOPEO_IMAGE:
                output = "sha256:tool"
            elif config_id is None:
                return SimpleNamespace(returncode=1, stdout="", stderr="image absent")
            else:
                output = config_id
        else:
            output = ""
        return SimpleNamespace(returncode=0, stdout=output, stderr="")
    monkeypatch.setattr(agent_images.subprocess, "run", run)
    monkeypatch.setattr(agent_images.shutil, "disk_usage", lambda _: SimpleNamespace(free=free))
    return calls


def test_missing_cache_fails_without_any_docker_call(tmp_path, monkeypatch):
    calls = fake_docker(monkeypatch, tmp_path)
    with pytest.raises(RuntimeError, match="agent_image_cache_missing"):
        agent_images.ensure_cached_images("mini", ["example/task:latest"], tmp_path)
    assert calls == []


def test_existing_image_is_reused_only_when_it_matches_cached_config(tmp_path, monkeypatch):
    _, config_id, _ = make_cache(tmp_path)
    calls = fake_docker(monkeypatch, tmp_path, config_id=config_id)
    assert agent_images.ensure_cached_images("mini", ["example/task:latest"], tmp_path) == {"example/task:latest": "example/task:latest"}
    assert not any(command[:2] == ["docker", "run"] for command in calls)


def test_insufficient_space_prevents_import(tmp_path, monkeypatch):
    make_cache(tmp_path)
    calls = fake_docker(monkeypatch, tmp_path, free=1024)
    with pytest.raises(RuntimeError, match="agent_image_disk_space"):
        agent_images.ensure_cached_images("mini", ["example/task:latest"], tmp_path)
    assert not any(command[:2] == ["docker", "run"] for command in calls)


def test_corrupted_oci_manifest_fails_before_import(tmp_path, monkeypatch):
    cache, _, _ = make_cache(tmp_path)
    descriptor = json.loads((cache / "images/index.json").read_text())["manifests"][0]
    (cache / "images/blobs/sha256" / descriptor["digest"].split(":")[1]).write_text("{}")
    calls = fake_docker(monkeypatch, tmp_path)
    with pytest.raises(RuntimeError, match="agent_image_cache_invalid"):
        agent_images.ensure_cached_images("mini", ["example/task:latest"], tmp_path)
    assert calls == []


def test_import_uses_only_local_oci_and_tool_without_network(tmp_path, monkeypatch):
    _, config_id, _ = make_cache(tmp_path)
    calls = fake_docker(monkeypatch, tmp_path)
    monkeypatch.setattr(agent_images, "image_id", lambda image: "sha256:tool" if image == agent_images.SKOPEO_IMAGE else
                        config_id if any(cmd[:2] == ["docker", "run"] for cmd in calls) else None)
    agent_images.ensure_cached_images("mini", ["example/task:latest"], tmp_path)
    command = next(cmd for cmd in calls if cmd[:2] == ["docker", "run"])
    assert command[command.index("--pull") + 1] == "never"
    assert command[command.index("--network") + 1] == "none"
    assert "oci:/cache/images:task-one" in command
    assert "docker-daemon:example/task:latest" in command
    assert not any(value.startswith("docker://") for value in command)


def test_entire_selection_is_checked_before_importing_first_image(tmp_path, monkeypatch):
    make_cache(tmp_path)
    calls = fake_docker(monkeypatch, tmp_path)
    with pytest.raises(RuntimeError, match="agent_image_cache_missing"):
        agent_images.ensure_cached_images("mini", ["example/task:latest", "example/missing:latest"], tmp_path)
    assert calls == []


def test_cache_cannot_reference_another_dataset_directory(tmp_path, monkeypatch):
    cache, _, _ = make_cache(tmp_path)
    manifest = json.loads((cache / "preparation.json").read_text())
    manifest["tasks"]["one"]["oci_reference"] = f"oci:{tmp_path / 'other/images'}:task-one"
    (cache / "preparation.json").write_text(json.dumps(manifest))
    calls = fake_docker(monkeypatch, tmp_path)
    with pytest.raises(RuntimeError, match="agent_image_cache_invalid"):
        agent_images.ensure_cached_images("mini", ["example/task:latest"], tmp_path)
    assert calls == []


def test_corrupted_layer_is_rejected_before_import(tmp_path, monkeypatch):
    cache, _, digest = make_cache(tmp_path)
    (cache / "images/blobs/sha256" / digest[7:]).write_bytes(b"corrupted")
    calls = fake_docker(monkeypatch, tmp_path)
    with pytest.raises(RuntimeError, match="agent_image_cache_invalid"):
        agent_images.ensure_cached_images("mini", ["example/task:latest"], tmp_path)
    assert not any(command[:2] == ["docker", "run"] for command in calls)


def test_mini_adapter_never_invokes_upstream_image_build_and_uses_selected_samples(tmp_path, monkeypatch):
    from app.intelligence.evalscope_direct import _load_evalscope_benchmarks
    from evalscope import TaskConfig
    from evalscope.api.dataset import Sample
    from evalscope.api.registry import get_benchmark
    from evalscope.benchmarks.swe_bench import build_images

    _load_evalscope_benchmarks()
    def forbidden(**kwargs):
        pytest.fail("upstream pull/build must never run")
    monkeypatch.setattr(build_images, "build_images", forbidden)
    imported = []
    monkeypatch.setattr(agent_images, "ensure_cached_images", lambda dataset, images, root: imported.extend(images))
    adapter = get_benchmark("swe_bench_verified_mini_agentic", TaskConfig(model="dummy", datasets=["swe_bench_verified_mini_agentic"],
        limit=1, dataset_args={"swe_bench_verified_mini_agentic": {"extra_params": {
            "project_image_cache": str(tmp_path), "build_docker_images": True, "pull_remote_images_if_available": True}}}))
    sample = Sample(input="Fix bug", metadata={"instance_id": "django__django-11790"})
    adapter.test_dataset = {adapter.default_subset: [sample]}
    adapter._post_process_samples()
    assert imported == [sample.metadata["docker_image"]]
    assert adapter.build_docker_images is False
    assert adapter.pull_remote_images_if_available is False
