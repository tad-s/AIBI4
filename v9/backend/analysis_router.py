"""
analysis_router.py — V9 built-in analysis endpoint.
POST /api/analysis/{sid}
"""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool

import session as sess
from analysis_service import run_all_analyses

router = APIRouter()


def _evidence_for_results(results: list[dict], df) -> list[dict]:
    entries = []
    for idx, item in enumerate(results, start=1):
        table = item.get("table") or []
        entries.append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": "base_analysis",
            "index": idx,
            "title": item.get("title"),
            "status": "ok" if item.get("image_b64") else "no_image",
            "graph_present": bool(item.get("image_b64")),
            "table_rows": len(table) if isinstance(table, list) else 0,
            "insights": item.get("insights") or [],
            "advice": item.get("advice") or [],
            "data_rows": int(len(df)) if df is not None else 0,
            "data_columns": list(map(str, df.columns)) if df is not None else [],
            "evidence_note": "This graph is generated from server-side computed aggregates. The returned table is the computed evidence behind the chart when available.",
        })
    return entries


@router.post("/analysis/{sid}")
async def run_analysis(sid: str):
    s = sess.get_session(sid)
    if not s:
        raise HTTPException(status_code=404, detail="セッションが見つかりません。")
    df = s.get("df")
    if df is None:
        raise HTTPException(status_code=400, detail="データが取得されていません。先にデータを取得してください。")

    results = await run_in_threadpool(run_all_analyses, df)
    existing_log = list(s.get("evidence_log") or [])
    evidence_entries = _evidence_for_results(results, df)
    sess.update_session(
        sid,
        analyses=results,
        analysis_results=results,
        evidence_log=existing_log + evidence_entries,
    )
    return {"analyses": results}
