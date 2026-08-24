from __future__ import annotations

from fastapi import APIRouter

from app.suites.profiles import EvalScopeProfileStore

router = APIRouter(prefix="/evalscope", tags=["evalscope"])


@router.get("/profiles")
def list_evalscope_profiles():
    return EvalScopeProfileStore().list()
