"""T1 PoC API."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from services.analysis import run_all
from services.base_table import build_base_table, read_base_table
from services.exporter import build_excel

router = APIRouter(prefix="/api")

_LAST_RESULT: dict | None = None
_LAST_FUNNEL: list[dict] | None = None


class BuildReq(BaseModel):
    force: bool = False


@router.get("/health")
def health():
    return {"status": "ok", "app": "T1", "version": "1.0.0"}


@router.post("/build")
def build(req: BuildReq):
    global _LAST_FUNNEL
    try:
        df, funnel = build_base_table(force=req.force)
        _LAST_FUNNEL = funnel
        return {"summary": {
            "rows": int(len(df)),
            "visits": int(df["visit_id"].nunique()),
            "orders": int(df["order_id"].nunique()),
            "items": int(df["item_name"].nunique()),
        }, "funnel": funnel}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/analyze")
def analyze():
    global _LAST_RESULT
    try:
        df = read_base_table()
        _LAST_RESULT = run_all(df)
        return _LAST_RESULT
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/export")
def export():
    global _LAST_RESULT
    try:
        if _LAST_RESULT is None:
            df = read_base_table()
            _LAST_RESULT = run_all(df)
        buf = build_excel(_LAST_RESULT, _LAST_FUNNEL)
        filename = f"T1_ikebukuro_poc_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
