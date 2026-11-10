from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.intelligence.config_store import EvalScopeConfigStore
from app.intelligence.evalscope_direct import (
    EvalScopeIntelligenceExecutor,
    configure_swebench_mirrors,
    datasets_root,
    swebench_cache_root,
)


def _load_samples(dataset: str, limit: int | None, work_dir: Path) -> list[Any]:
    from evalscope import TaskConfig
    from evalscope.api.registry import get_benchmark
    from evalscope.benchmarks.swe_bench.build_images import build_images

    config = EvalScopeConfigStore().load()
    executor = EvalScopeIntelligenceExecutor(config)
    local_path = datasets_root(config) / dataset
    if not local_path.is_dir():
        raise SystemExit(f"dataset_missing:{local_path}")
    dataset_args = executor._dataset_args(
        dataset=dataset, local_paths={dataset: str(local_path)}
    )
    task_config = TaskConfig(
        model="offline-prewarm",
        datasets=[dataset],
        dataset_args=dataset_args,
        limit=limit,
        eval_batch_size=1,
        work_dir=str(work_dir),
    )
    adapter = get_benchmark(dataset, task_config)
    test_data, _ = adapter.load()
    samples = list(next(iter(test_data.values())))
    extra_params = adapter.extra_params
    images = build_images(
        samples=samples,
        max_workers=4,
        force_rebuild=False,
        use_remote_images=extra_params.get("pull_remote_images_if_available", True),
        force_arch=extra_params.get("force_arch", ""),
        dockerhub_username=extra_params.get("dockerhub_username") or "swebench",
    )
    for sample in samples:
        sample.metadata["docker_image"] = images[sample.metadata["instance_id"]]
    return samples


def _inspect_image(image: str) -> dict[str, Any] | None:
    result = subprocess.run(
        ["docker", "image", "inspect", image, "--format", "{{json .}}"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    payload = json.loads(result.stdout)
    return {
        "id": payload.get("Id"),
        "repo_digests": payload.get("RepoDigests") or [],
        "size": payload.get("Size"),
    }


def _write_manifest(dataset: str, images: dict[str, str], cache_dir: Path) -> Path:
    inspected = {instance_id: {"image": image, "inspect": _inspect_image(image)} for instance_id, image in images.items()}
    missing = [instance_id for instance_id, row in inspected.items() if row["inspect"] is None]
    if missing:
        raise SystemExit(f"images_missing:{', '.join(missing)}")
    manifest_path = cache_dir / f"manifest-{dataset}.json"
    temp_path = manifest_path.with_suffix(f".{os.getpid()}.tmp")
    temp_path.write_text(
        json.dumps(
            {"dataset": dataset, "sample_count": len(images), "images": inspected},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    os.replace(temp_path, manifest_path)
    return manifest_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Pre-pull SWE-bench images and cache task metadata for offline evaluation.")
    parser.add_argument("--dataset", default="swe_bench_verified_mini_agentic")
    parser.add_argument("--limit", type=int, default=1, help="Number of instance images to prepare; use 50 for a complete Mini offline run.")
    parser.add_argument("--offline-check", action="store_true")
    args = parser.parse_args()

    cache_dir = swebench_cache_root()
    cache_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = cache_dir / f"manifest-{args.dataset}.json"
    if args.offline_check:
        if not manifest_path.is_file():
            raise SystemExit(f"manifest_missing:{manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        missing = [
            instance_id
            for instance_id, row in manifest["images"].items()
            if _inspect_image(row["image"]) is None
        ]
        if missing:
            raise SystemExit(f"images_missing:{', '.join(missing)}")
        os.environ["LLM_BENCHMARK_SWEBENCH_OFFLINE"] = "1"
    else:
        os.environ.pop("LLM_BENCHMARK_SWEBENCH_OFFLINE", None)

    configure_swebench_mirrors()
    samples = _load_samples(args.dataset, args.limit, cache_dir / "prewarm" / args.dataset)
    images = {sample.metadata["instance_id"]: sample.metadata["docker_image"] for sample in samples}
    if not args.offline_check:
        manifest_path = _write_manifest(args.dataset, images, cache_dir)
    print(f"offline_ready dataset={args.dataset} samples={len(samples)} manifest={manifest_path}")


if __name__ == "__main__":
    main()
