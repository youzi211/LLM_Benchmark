#!/usr/bin/env python
"""Download EvalScope perf datasets to data/stress_datasets so stress runs never need network.

Usage:
    .venv/bin/python scripts/download_stress_dataset.py longalpaca
    .venv/bin/python scripts/download_stress_dataset.py longalpaca openqa
    .venv/bin/python scripts/download_stress_dataset.py --all

After download, submit a stress task with the matching dataset name and the runner
will auto-fill dataset_path to data/stress_datasets/<name>.json, so EvalScope's
plugin reads the local file (``dataset_json_list`` -> ``json.loads`` of a JSON
array) instead of pulling from ModelScope each run.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Default root, overridable via LLM_BENCHMARK_STRESS_DATASETS_DIR (same env as the runner).
DEFAULT_ROOT = Path(os.getenv("LLM_BENCHMARK_STRESS_DATASETS_DIR", "data/stress_datasets"))

# Per-dataset record normalizer.  Each plugin reads a specific key from each
# record; we keep only that key so the local file stays small and matches the
# shape ``dataset_json_list`` + the plugin's ``build_messages`` expect.
def _keep_instruction(item: dict) -> dict | None:
    """Keep only ``{"instruction"}`` (the key the longalpaca plugin reads)."""
    instr = item.get("instruction")
    if not instr:
        # Fall back to the first text-like field for splits that key differently.
        for key in ("text", "prompt", "input", "question"):
            if item.get(key):
                instr = item[key]
                break
    if not instr:
        return None
    return {"instruction": str(instr).strip()}


# (dataset_name, dataset_id, split, normalize_fn)
#   We load the dataset via ``load_dataset_from_hub`` (which resolves ModelScope
#   metadata pointers to real Arrow records), normalize each row, and write the
#   result as a single JSON array into <root>/<name>.json.  That matches the
#   ``dataset_json_list`` path in the plugin (``json.loads`` of a JSON array).
DATASETS: dict[str, tuple[str, str, callable]] = {
    "longalpaca": ("AI-ModelScope/LongAlpaca-12k", "train", _keep_instruction),
    # Add more here as needed (openqa, share_gpt_*, ...). Each name must also be
    # listed in app/stress.runner.LOCAL_RESOLVABLE_DATASETS for the runner to
    # auto-resolve data/stress_datasets/<name>.json.
}


def download_hub_dataset(root: Path, name: str, dataset_id: str, split: str, normalize) -> Path:
    """Load a hub dataset, normalize rows, write a JSON array to <root>/<name>.json.

    The output is a single JSON array (not JSONL) because the EvalScope plugin's
    ``dataset_json_list`` does ``json.loads`` over the whole file and iterates
    the resulting list.  JSONL (one object per line) would fail that parse.
    """
    from evalscope.api.dataset.hub import load_dataset_from_hub  # type: ignore
    from evalscope.constants import HubType  # type: ignore

    root.mkdir(parents=True, exist_ok=True)
    dest = root / f"{name}.json"
    print(f"[{name}] loading {dataset_id} split={split} via ModelScope ...")
    ds = load_dataset_from_hub(
        data_id_or_path=dataset_id,
        split=split,
        data_source=HubType.MODELSCOPE,
    )
    records = []
    dropped = 0
    for item in ds:
        norm = normalize(dict(item))
        if norm is None:
            dropped += 1
            continue
        records.append(norm)
    if not records:
        raise RuntimeError(f"[{name}] no usable records after normalization")
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False)
    print(f"[{name}] wrote {len(records)} records ({dropped} dropped) -> {dest}")
    return dest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "names",
        nargs="*",
        help="dataset name(s) to download (e.g. longalpaca). Use --all for every entry.",
    )
    parser.add_argument("--all", action="store_true", help="download every dataset in DATASETS")
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
        help=f"destination root (default: {DEFAULT_ROOT})",
    )
    args = parser.parse_args()

    if args.all:
        names = list(DATASETS)
    elif args.names:
        unknown = [n for n in args.names if n not in DATASETS]
        if unknown:
            print(f"unknown dataset(s): {', '.join(unknown)}", file=sys.stderr)
            print(f"available: {', '.join(DATASETS)}", file=sys.stderr)
            return 2
        names = args.names
    else:
        parser.print_help(sys.stderr)
        return 2

    failed = []
    for name in names:
        dataset_id, split, normalize = DATASETS[name]
        try:
            download_hub_dataset(args.root, name, dataset_id, split, normalize)
        except Exception as exc:  # noqa: BLE001 - report per-dataset failure, keep going
            print(f"[{name}] FAILED: {exc}", file=sys.stderr)
            failed.append(name)

    if failed:
        print(f"\nFailed: {', '.join(failed)}", file=sys.stderr)
        return 1
    print("\nDone. Submit stress with dataset=<name>; the runner will auto-resolve the local path.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
