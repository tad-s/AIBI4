"""分析結果の Excel エクスポート（データ＋根拠シート）。"""
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core import export as xlsx
from core.duck import store
from routers.query import _run
from semantic import engine
from semantic.query import Filters, QuerySpec

router = APIRouter(prefix="/api")


class ExportReq(BaseModel):
    spec: QuerySpec
    global_filters: Filters | None = None
    confidence: float | None = None


@router.post("/sessions/{sid}/export")
def export_xlsx(sid: str, req: ExportReq):
    session = store.get(sid)
    if session is None:
        raise HTTPException(status_code=404, detail="セッションが見つかりません。")
    try:
        result = _run(session, req.spec, req.global_filters)
    except engine.SpecError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    data = xlsx.build_report(result, req.confidence)

    # ファイル名（日本語対応: RFC5987 filename*）
    title = (result.get("title") or "分析結果").replace("/", "_").replace("\\", "_")
    fname = quote(f"{title}.xlsx")
    headers = {
        "Content-Disposition": f"attachment; filename=analysis.xlsx; filename*=UTF-8''{fname}",
    }
    return StreamingResponse(
        iter([data]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )
