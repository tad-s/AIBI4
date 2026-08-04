"""テング池袋東口店 PoC 分析エンドポイント。

POST /api/poc/analysis/{sid}
  生CSV(order粒度)から除外適用済みテーブルを構築し、4分析(+カテゴリ版)を返す。
  ベース分析と同じ card 形式なので、フロントは analysis-grid にそのまま差し替え表示できる。
"""
from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool

import session as sess
from poc import base_table
from poc.analyses import run_poc_analyses

router = APIRouter()


@router.get("/poc/available")
def poc_available():
    return {"available": base_table.available()}


@router.post("/poc/analysis/{sid}")
async def run_poc(sid: str):
    if not base_table.available():
        raise HTTPException(status_code=404,
                            detail="PoC用データ(池袋東口店の生テーブル)が見つかりません。")
    s = sess.get_session(sid)
    if not s:
        raise HTTPException(status_code=404, detail="セッションが見つかりません。")

    df = await run_in_threadpool(base_table.build)
    results = await run_in_threadpool(run_poc_analyses, df)

    meta = {
        "store": "テング酒場 池袋東口店",
        "period": "2026-03 〜 2026-05",
        "visits": int(df["visit_id"].nunique()),
        "orders": int(df["order_id"].nunique()),
        "items": int(len(df)),
        "note": "全日14-23時（日曜22時まで）・単独客/ランチ定食/対象外メニュー/コース・放題を除外",
    }
    # ベース分析と同様にセッションへ保存（エビデンス/エクスポートとの整合）
    sess.update_session(sid, analyses=results, analysis_results=results, poc_meta=meta)
    return {"analyses": results, "meta": meta}
