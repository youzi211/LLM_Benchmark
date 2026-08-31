from __future__ import annotations

import os
import time
from pathlib import Path

from fastapi import APIRouter

from app.storage.model_store import ModelStore

router = APIRouter(prefix="/health", tags=["health"])

_REPO_ROOT = Path(__file__).resolve().parents[2]
_EVALSCOPE_DATASETS = _REPO_ROOT / "data" / "evalscope_datasets"
_T0 = time.time()


def _evalstore_status() -> dict:
    """检查 EvalScope 路径是否就绪. 不发起实际推理, 仅做配置就绪度检查."""
    return {
        "datasets_dir": str(_EVALSCOPE_DATASETS),
        "datasets_dir_exists": _EVALSCOPE_DATASETS.is_dir(),
        "scheduler_disabled": bool(os.environ.get("LLM_BENCHMARK_SCHEDULER_DISABLED")),
    }


@router.get("")
def health():
    """整体服务健康快照. 不消耗外部资源, 适合高频轮询."""
    uptime_s = round(time.time() - _T0, 1)
    model_store = ModelStore()
    models = model_store.list() if hasattr(model_store, "list") else []
    return {
        "status": "ok",
        "uptime_s": uptime_s,
        "scheduler_disabled": bool(os.environ.get("LLM_BENCHMARK_SCHEDULER_DISABLED")),
        "models": {
            "ok": True,
            "count": len(models) if isinstance(models, list) else 0,
        },
        "evalscope": {
            # 配置就绪: 数据集目录存在即视为"就绪但未运行", 这与原始的"未运行"语义一致
            "ok": _EVALSCOPE_DATASETS.is_dir(),
            "state": "ready" if _EVALSCOPE_DATASETS.is_dir() else "missing_datasets",
            "datasets_dir": str(_EVALSCOPE_DATASETS),
        },
        "scheduler": {
            "ok": not bool(os.environ.get("LLM_BENCHMARK_SCHEDULER_DISABLED")),
            "state": "disabled" if os.environ.get("LLM_BENCHMARK_SCHEDULER_DISABLED") else "running",
        },
    }
