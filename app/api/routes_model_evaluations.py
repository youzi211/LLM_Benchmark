from typing import Literal

from fastapi import APIRouter, Query
from app.api.errors import api_error
from app.overview.model_evaluations import ComparisonRequest, ModelEvaluations, Lane

router = APIRouter(tags=["model-evaluations"])


@router.get("/model-evaluations")
def list_model_evaluations(search: str = "", include_archived: bool = False,
                           page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
                           sort_by: Literal["model_id", "coverage", "last_execution"] = "model_id",
                           order: Literal["asc", "desc"] = "asc"):
    service = ModelEvaluations()
    items = [service.detail(id) for id in sorted(service.models.keys() | service.tasks.keys())]
    items = [m for m in items if (include_archived or not m["archived"])
             and search.casefold() in (m["model_id"] + " " + m["name"]).casefold()]
    if sort_by == "last_execution":
        known = [m for m in items if m["last_execution_at"] is not None]
        unknown = [m for m in items if m["last_execution_at"] is None]
        items = sorted(known, key=lambda m: m["last_execution_at"], reverse=order == "desc") + unknown
    else:
        items.sort(key=lambda m: m[sort_by], reverse=order == "desc")
    return {"total": len(items), "page": page, "page_size": page_size,
            "items": items[(page - 1) * page_size:page * page_size]}


@router.get("/model-evaluations/{model_id}")
def model_evaluation(model_id: str):
    try:
        return ModelEvaluations().detail(model_id)
    except KeyError:
        raise api_error(404, "model_not_found", "模型及历史记录不存在")


@router.get("/model-evaluations/{model_id}/history")
def model_history(model_id: str, lane: Lane | None = None,
                  page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100)):
    try:
        return ModelEvaluations().history(model_id, lane, page, page_size)
    except KeyError:
        raise api_error(404, "model_not_found", "模型及历史记录不存在")


@router.post("/model-comparisons")
def compare_models(request: ComparisonRequest):
    try:
        return ModelEvaluations().compare(request)
    except KeyError:
        raise api_error(404, "model_not_found", "模型及历史记录不存在")
    except ValueError as exc:
        raise api_error(422, "invalid_comparison_task", str(exc))
