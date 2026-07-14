"""ベース分析・注文導線分析エンドポイント。"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from analyses.runner import run_all
from core.duck import store
from semantic.query import Filters

router = APIRouter(prefix="/api")


class AnalysesReq(BaseModel):
    global_filters: Filters | None = None


@router.post("/sessions/{sid}/analyses")
def analyses(sid: str, req: AnalysesReq):
    session = store.get(sid)
    if session is None:
        raise HTTPException(status_code=404, detail="セッションが見つかりません。")
    try:
        return run_all(session, req.global_filters)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
