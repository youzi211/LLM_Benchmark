"""Small display contract; the original report remains the evidence archive."""
import math
from typing import Any


def primary_summary(payload: dict[str, Any]) -> dict[str, Any]:
    legacy = payload.get("schema_version", 1) != 2
    result: dict[str, Any] = {"score": None, "metric_id": None, "unit": None,
                              "direction": None, "sample_count": None, "display_multiplier": 1.0,
                              "complete": None, "unavailable_reason": None}
    try:
        from evalscope.report.report import Report
        report = Report.from_dict(payload)
        metric = getattr(report, "primary_metric", None)
        if metric is not None:
            semantics = metric.semantics
            result.update(score=metric.score, metric_id=metric.identity.key,
                          unit=semantics.display_unit or semantics.raw_unit,
                          direction=semantics.direction.value, sample_count=metric.num,
                          display_multiplier=semantics.display_multiplier or 1.0)
        else:
            result["unavailable_reason"] = getattr(report, "primary_metric_unavailable_reason", None) or "未声明主指标"
        execution = getattr(report, "execution_summary", None)
        if execution is not None:
            result["complete"] = not execution.incomplete and execution.errored == 0
    except (ImportError, ValueError, TypeError, AttributeError):
        result["unavailable_reason"] = "报告格式无法解析"
    # Old project snapshots sometimes contain only the explicit top-level score.
    if legacy and result["score"] is None and isinstance(payload.get("score"), (int, float)):
        result.update(score=payload["score"], unavailable_reason=None)
    if result["score"] is not None and (isinstance(result["score"], bool) or not math.isfinite(result["score"])):
        result.update(score=None, unavailable_reason="非有限数值")
    return result
