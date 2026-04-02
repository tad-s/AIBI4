"""
analysis_router.py — 6項目分析エンドポイント
POST /api/analysis/{sid}  6項目の分析を実行して結果を返す
"""
from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool

import session as sess
from analysis_service import run_all_analyses

router = APIRouter()


@router.post("/analysis/{sid}")
async def run_analysis(sid: str):
    s = sess.get_session(sid)
    if not s:
        raise HTTPException(status_code=404, detail="セッションが見つかりません。")
    df = s.get("df")
    if df is None:
        raise HTTPException(status_code=400, detail="データが取得されていません。先にデータを取得してください。")

    results = await run_in_threadpool(run_all_analyses, df)
    return {"analyses": results}
