from __future__ import annotations

from typing import Any

from app.intelligence.evalscope_direct import outputs_root, _to_plain
from app.intelligence.schemas import EvalScopeConfig
from app.reports.markdown import redact_text
from app.stress.schemas import StressRemoteSubmitPayload


class EvalScopeStressExecutor:
    def __init__(self, config: EvalScopeConfig):
        self.config = config

    def run(self, *, task_id: str, payload: StressRemoteSubmitPayload) -> dict[str, Any]:
        try:
            from evalscope.perf.arguments import Arguments  # type: ignore
            from evalscope.perf.main import run_perf_benchmark  # type: ignore
        except Exception as exc:  # pragma: no cover - depends on optional local install
            raise RuntimeError(f"evalscope_perf_import_failed:{redact_text(str(exc))}") from exc

        data = payload.model_dump(mode="json")
        data["outputs_dir"] = str(outputs_root(self.config) / "stress" / task_id)
        data["enable_progress_tracker"] = True
        args = Arguments(**data)
        result = run_perf_benchmark(args)
        if isinstance(result, dict):
            raw = result
        else:
            raw = {"result": result}
        # EvalScope perf 在运行期返回的 metrics / percentiles 等是 pydantic 对象
        # （BenchmarkSummary / PercentileResult），并非纯 dict。若直接交给下游
        # _perf_mapping_rows 解析，后者按 dict 判定会跳过这些档位，导致标准化
        # runs 为空、报告档位表和"一眼看懂"全部显示 "-"。这里先递归扁平化为
        # 纯 dict/list，保证持久化与解析一致。
        raw = _to_plain(raw)
        raw.setdefault("task_id", task_id)
        raw.setdefault("model", payload.model)
        raw.setdefault("status", "completed")
        return raw
