from fastapi import APIRouter, Query
from app.api.errors import api_error
from app.overview.model_evaluations import ComparisonRequest, ModelEvaluations, Lane

router = APIRouter(tags=["model-evaluations"])


@router.get("/model-evaluations")
def list_model_evaluations(search: str = "", include_archived: bool = False,
                           page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100)):
    service = ModelEvaluations()
    items = [service.detail(id) for id in sorted(service.models.keys() | service.tasks.keys())]
    items = [m for m in items if (include_archived or not m["archived"])
             and search.casefold() in (m["model_id"] + " " + m["name"]).casefold()]
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
