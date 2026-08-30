#!/usr/bin/env python3
"""下载 ChartQA 数据集并保存为 datasets.load_dataset 可识别的 parquet 格式。

保留全部列（含 ChartQAAdapter 切子集所需的 ``type`` 列）和 Image 字节，不做自定义子集拆分。
EvalScope 加载本地路径时走 ``datasets.load_dataset(path=<dir>, split='test')``，
因此目录里需要是 parquet/csv/jsonl 等数据文件，而不是 ``datasets.save_to_disk()`` 产生的 arrow 格式
（后者只能用 ``load_from_disk`` 加载，会被 ``load_dataset`` 拒绝）。
"""

from pathlib import Path

DATA_DIR = Path("data/evalscope_datasets/chartqa")


def download_and_save():
    print("=== 步骤1: 从 ModelScope 下载 ChartQA ===")
    from modelscope import MsDataset
    import datasets

    print("下载 lmms-lab/ChartQA ...")
    ds = MsDataset.load("lmms-lab/ChartQA", split="test")
    if not isinstance(ds, datasets.Dataset):
        ds = ds.to_hf_dataset()
    print(f"下载完成，共 {len(ds)} 条数据，列: {ds.column_names}")
    assert "type" in ds.column_names, "官方数据缺少 type 列，无法切子集"

    print(f"\n=== 步骤2: 保存到 {DATA_DIR} ===")
    import shutil

    if DATA_DIR.exists():
        shutil.rmtree(DATA_DIR)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    # 直接保存官方原始 parquet，保留 type/question/answer/image 全部列与 Image 字节。
    parquet_path = DATA_DIR / "test-00000-of-00001.parquet"
    ds.to_parquet(str(parquet_path))

    print("\n=== 步骤3: 验证（用 EvalScope 实际使用的 load_dataset 路径）===")
    verified = datasets.load_dataset(path=str(DATA_DIR), split="test")
    print(f"  行数: {len(verified)}")
    print(f"  列: {verified.column_names}")
    assert "type" in verified.column_names, "type 列丢失！"
    import collections

    print(f"  type 分布: {dict(collections.Counter(verified['type']))}")
    print("\n=== 完成! ===")


if __name__ == "__main__":
    download_and_save()
