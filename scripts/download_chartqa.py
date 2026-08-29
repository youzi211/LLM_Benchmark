#!/usr/bin/env python3
"""下载 ChartQA 数据集并按子集拆分为 parquet 文件，与现有 bbh/ceval 结构一致。"""

import os
import shutil
from pathlib import Path

DATA_DIR = Path("/data1/yzc/LLM_Benchmark/data/evalscope_datasets/chartqa")
SYMLINK_DIR = Path("/data1/yzc/LLM_test/LLM_Benchmark/data/evalscope_datasets/chartqa")


def download_and_split():
    print("=== 步骤1: 从 ModelScope 下载 ChartQA ===")
    from modelscope import MsDataset
    import datasets

    print("下载 lmms-lab/ChartQA...")
    ds = MsDataset.load("lmms-lab/ChartQA", split="test")
    if not isinstance(ds, datasets.Dataset):
        ds = ds.to_hf_dataset()
    print(f"下载完成，共 {len(ds)} 条数据")

    import pandas as pd
    type_counts = ds.to_pandas()["type"].value_counts().to_dict()
    print(f"子集分布: {type_counts}")

    print("\n=== 步骤2: 按子集拆分为 parquet ===")
    if DATA_DIR.exists():
        shutil.rmtree(DATA_DIR)
    if SYMLINK_DIR.exists() or SYMLINK_DIR.is_symlink():
        SYMLINK_DIR.unlink()

    df = ds.to_pandas()
    for subset_name in ["human_test", "augmented_test"]:
        subset_df = df[df["type"] == subset_name]
        subset_dir = DATA_DIR / subset_name
        subset_dir.mkdir(parents=True, exist_ok=True)
        parquet_path = subset_dir / "test-00000-of-00001.parquet"
        subset_df[["question", "answer", "image"]].to_parquet(str(parquet_path), index=False)
        print(f"  {subset_name}: {len(subset_df)} 条 -> {parquet_path}")

    print(f"\n=== 步骤3: 创建软链接 ===")
    SYMLINK_DIR.parent.mkdir(parents=True, exist_ok=True)
    SYMLINK_DIR.symlink_to(DATA_DIR)
    print(f"  {SYMLINK_DIR} -> {DATA_DIR}")

    print("\n=== 完成! ===")
    for subset in ["human_test", "augmented_test"]:
        p = DATA_DIR / subset / "test-00000-of-00001.parquet"
        verify = pd.read_parquet(str(p))
        print(f"  {subset}: {len(verify)} 条, 列: {list(verify.columns)}")


if __name__ == "__main__":
    download_and_split()