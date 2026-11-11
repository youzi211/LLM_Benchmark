"""Import selected Agent images from the project's OCI cache, never a registry."""
from __future__ import annotations

import gzip
import hashlib
import json
import logging
from pathlib import Path
import re
import shutil
import subprocess
import threading
import uuid

SKOPEO_IMAGE = "quay.nju.edu.cn/skopeo/stable@sha256:81a8d4265c339539cba229459fdc4cb3580e1d2c2cb4285271c75adaa0fcb9b5"
DISK_RESERVE = 10 * 1024**3
_import_lock = threading.Lock()
logger = logging.getLogger(__name__)


def image_id(image: str) -> str | None:
    result = subprocess.run(["docker", "image", "inspect", "--format", "{{.Id}}", image],
                            capture_output=True, text=True, timeout=30)
    return result.stdout.strip() if result.returncode == 0 else None


def _blob(images: Path, descriptor: dict) -> Path:
    digest = descriptor.get("digest", "")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise ValueError("invalid OCI digest")
    path = (images / "blobs/sha256" / digest[7:]).resolve()
    if not path.is_relative_to(images.resolve()) or not path.is_file():
        raise ValueError("missing OCI blob")
    return path


def _json_blob(images: Path, descriptor: dict) -> dict:
    payload = _blob(images, descriptor).read_bytes()
    if hashlib.sha256(payload).hexdigest() != descriptor["digest"][7:]:
        raise ValueError("OCI digest mismatch")
    return json.loads(payload)


def _cached_image(cache: Path, row: dict, image: str) -> dict:
    reference = row.get("oci_reference", "")
    location, separator, tag = reference.removeprefix("oci:").rpartition(":")
    images = Path(location).resolve()
    if not reference.startswith("oci:") or not separator or not images.is_relative_to(cache):
        raise ValueError("OCI reference must stay inside the dataset cache")
    index = json.loads((images / "index.json").read_text())
    descriptor = next(item for item in index["manifests"]
                      if item.get("annotations", {}).get("org.opencontainers.image.ref.name") == tag)
    if "@" in image and descriptor["digest"] != image.split("@", 1)[1]:
        raise ValueError("pinned image digest does not match OCI cache")
    manifest = _json_blob(images, descriptor)
    config = _json_blob(images, manifest["config"])
    if config.get("os") != "linux" or config.get("architecture") != "amd64":
        raise ValueError("expected linux/amd64 OCI image")
    layers = [(item, _blob(images, item)) for item in manifest["layers"]]
    # A local alias avoids Docker resolving a registry digest after OCI import.
    target = image if "@" not in image else "llm-benchmark-offline:" + descriptor["digest"][7:]
    return {"source": f"oci:/cache/{images.relative_to(cache).as_posix()}:{tag}", "target": target,
            "config_id": manifest["config"]["digest"], "layers": layers}


def _unpacked_bytes(descriptor: dict, path: Path) -> int:
    with path.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != descriptor["digest"][7:]:
            raise RuntimeError(f"agent_image_cache_invalid: layer checksum mismatch {path.name}")
    media = descriptor.get("mediaType", "")
    if media.endswith("+gzip") or media.endswith(".gzip"):
        size = 0
        with gzip.open(path, "rb") as stream:
            while block := stream.read(1024 * 1024):
                size += len(block)
        return size
    if media.endswith(".tar"):
        return path.stat().st_size
    raise RuntimeError(f"agent_image_cache_invalid: unsupported layer compression {media}")


def check_disk_space(required: int = 0) -> None:
    result = subprocess.run(["docker", "info", "--format", "{{.DockerRootDir}}"],
                            check=True, capture_output=True, text=True, timeout=30)
    root = Path(result.stdout.strip())
    free = shutil.disk_usage(root).free
    if free < required + DISK_RESERVE:
        raise RuntimeError(f"agent_image_disk_space: Docker {root} free={free / 1024**3:.1f} GiB; "
                           f"need {required / 1024**3:.1f} GiB plus 10 GiB reserve; import stopped")


def ensure_cached_images(dataset: str, images: list[str], cache_root: Path) -> dict[str, str]:
    """Sequentially import only the selected images; keep them for later reuse."""
    if not images:
        return {}
    cache = (cache_root / dataset).resolve()
    try:
        preparation = json.loads((cache / "preparation.json").read_text())
    except FileNotFoundError as exc:
        raise RuntimeError(f"agent_image_cache_missing:{dataset}; prepare local OCI images first; registry pulls disabled") from exc
    plans = {}
    try:
        rows = list(preparation["tasks"].values())
        for image in dict.fromkeys(images):
            row = next((row for row in rows if row.get("image") == image and row.get("image_cached")), None)
            if row is None:
                raise RuntimeError(f"agent_image_cache_missing:{dataset}:{image}; registry pulls disabled")
            plans[image] = _cached_image(cache, row, image)
    except (OSError, ValueError, KeyError, TypeError, StopIteration) as exc:
        raise RuntimeError(f"agent_image_cache_invalid:{dataset}:{exc}") from exc
    with _import_lock:
        pending = [plan for plan in plans.values() if image_id(plan["target"]) != plan["config_id"]]
        layers = {item["digest"]: (item, path) for plan in pending for item, path in plan["layers"]}
        # Include transfer scratch space as well as the unpacked layers.
        sizes = {digest: _unpacked_bytes(item, path) + path.stat().st_size for digest, (item, path) in layers.items()}
        required = sum(sizes.values())
        check_disk_space(required)
        if pending and image_id(SKOPEO_IMAGE) is None:
            raise RuntimeError("agent_image_tool_missing: load the cached Skopeo tool first; registry pulls disabled")
        for number, plan in enumerate(pending, 1):
            check_disk_space(required)
            logger.info("Importing offline Agent image %s/%s: %s", number, len(pending), plan["target"])
            name = "benchmark-image-import-" + uuid.uuid4().hex[:12]
            try:
                subprocess.run(["docker", "run", "--rm", "--name", name, "--pull", "never", "--network", "none",
                                "-v", f"{cache}:/cache:ro", "-v", "/var/run/docker.sock:/var/run/docker.sock",
                                SKOPEO_IMAGE, "--insecure-policy", "copy", plan["source"],
                                "docker-daemon:" + plan["target"]], check=True, timeout=900)
            finally:
                subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=30)
            if image_id(plan["target"]) != plan["config_id"]:
                raise RuntimeError(f"agent_image_import_invalid:{plan['target']}")
            for item, _ in plan["layers"]:
                required -= sizes.pop(item["digest"], 0)
    return {image: plan["target"] for image, plan in plans.items()}


def register_offline_mini() -> None:
    from evalscope.api.registry import BENCHMARK_REGISTRY

    meta = BENCHMARK_REGISTRY["swe_bench_verified_mini_agentic"]
    if getattr(meta.data_adapter, "_project_offline_images", False):
        return

    class OfflineMiniAdapter(meta.data_adapter):
        _project_offline_images = True

        def _post_process_samples(self):
            self.build_docker_images = False
            self.pull_remote_images_if_available = False
            super()._post_process_samples()
            samples = self.test_dataset[self.default_subset]
            ensure_cached_images(self.name, [sample.metadata["docker_image"] for sample in samples],
                                 Path(self.extra_params["project_image_cache"]))

    meta.data_adapter = OfflineMiniAdapter
    meta.extra_params["project_image_cache"] = {"type": "str", "description": "Project offline OCI cache", "value": "data/agent_image_cache"}
