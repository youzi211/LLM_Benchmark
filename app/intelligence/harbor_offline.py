"""Harbor Docker environments whose images can only come from local OCI cache."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import tempfile

from harbor.environments.docker.docker import DockerEnvironment

from app.intelligence.agent_images import ensure_cached_images


class OfflineDockerEnvironment(DockerEnvironment):
    def __init__(self, *, image_cache_root: str, dataset: str, **kwargs):
        super().__init__(**kwargs)
        self.image_cache_root = Path(image_cache_root)
        self.dataset = dataset
        self._offline_compose_dir = tempfile.TemporaryDirectory(prefix="benchmark-offline-images-")
        self._offline_sources = {}

    async def start(self, force_build: bool):
        if force_build:
            raise RuntimeError("agent_image_build_disabled: use prepared OCI images")
        if not (self.image_cache_root / self.dataset / "preparation.json").is_file():
            raise RuntimeError(f"agent_image_cache_missing:{self.dataset}; registry pulls and builds disabled")
        await super().start(force_build=False)

    async def _ensure_egress_control_sidecar_image_built(self):
        image = self._EGRESS_CONTROL_SIDECAR_DOCKER_NAME
        mapping = await asyncio.to_thread(ensure_cached_images, self.dataset, [image], self.image_cache_root)
        self._env_vars.egress_control_sidecar_image_name = mapping[image]
        self._offline_sources[mapping[image]] = image

    async def _run_docker_compose_command(self, command, **kwargs):
        if command[0] in {"pull", "build"}:
            raise RuntimeError("agent_image_build_disabled: registry pulls and builds disabled; use prepared OCI images")
        if command[0] == "up":
            resolved = await super()._run_docker_compose_command(["config", "--format", "json"])
            services = json.loads(resolved.stdout)["services"]
            images = [self._offline_sources.get(service.get("image"), service.get("image")) for service in services.values()]
            if not all(images):
                raise RuntimeError("agent_image_cache_missing: Compose service requires a prepared image; builds disabled")
            # Resolve every service, including independent verifier and auxiliary containers.
            mapping = await asyncio.to_thread(ensure_cached_images, self.dataset, images, self.image_cache_root)
            overlay = Path(self._offline_compose_dir.name) / "images.json"
            overlay.write_text(json.dumps({"services": {
                name: {"image": mapping[self._offline_sources.get(service["image"], service["image"])], "pull_policy": "never"}
                for name, service in services.items()
            }}))
            if overlay not in self.extra_docker_compose_paths:
                self.extra_docker_compose_paths.append(overlay)
            self._offline_sources.update({target: source for source, target in mapping.items()})
            command = [*command, "--pull", "never", "--no-build"]
        return await super()._run_docker_compose_command(command, **kwargs)

    async def stop(self, delete: bool):
        try:
            await super().stop(delete=delete)
        finally:
            self._offline_compose_dir.cleanup()
