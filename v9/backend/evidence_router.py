"""
evidence_router.py — V9 evidence log download endpoint.

GET /api/sessions/{sid}/evidence-log
Returns JSON containing chat history, analysis result metadata, validation notes,
and reproducibility evidence based on source data row/column counts and computed tables.
"""
import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

import session as sess

router = APIRouter()


@router.get("/sessions/{sid}/evidence-log")
def download_evidence_log(sid: str):
    s = sess.get_session(sid)
    if not s:
        raise HTTPException(status_code=404, detail="セッションが見つかりません。")
    df = s.get("df")
    payload = {
        "session_id": sid,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "data_profile": {
            "rows": int(len(df)) if df is not None else 0,
            "columns": list(map(str, df.columns)) if df is not None else [],
        },
        "chat_history": s.get("chat_history") or [],
        "chat_analyses": s.get("chat_analyses") or [],
        "base_analyses": s.get("analysis_results") or [],
        "evidence_log": s.get("evidence_log") or [],
        "validation_policy": {
            "graph_generation": "Graphs are generated from in-memory df or server-side computed analysis tables.",
            "file_read_guard": "Generated chat graph code is sanitized; pd.read_csv/read_excel/open calls are blocked.",
            "table_consistency": "Each base analysis stores the computed table rows returned by the analysis function; exported evidence records table row counts and graph presence.",
            "limitations": "Image pixels are not reverse-validated. Evidence validates the computed source table/metadata used to create each graph.",
        },
    }
    data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    return StreamingResponse(
        iter([data]),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=AIBI4_V9_evidence_log.json"},
    )
