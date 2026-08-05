"""テング池袋東口店 PoC 分析エンドポイント。

POST /api/poc/analysis/{sid}      … 4分析(+カテゴリ版)を実行して返す
GET  /api/poc/evidence/{sid}      … データ来歴（原本CSV→変換→集計）テキストをDL
GET  /api/poc/categories          … カテゴリ内訳（ドリルダウン用）
POST /api/poc/categories/override … 商品のカテゴリを編集（PoC専用テーブルを更新・原本不変）
"""
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel

import session as sess
from poc import base_table, lineage
from poc.analyses import run_poc_analyses

router = APIRouter()


def _meta(df) -> dict:
    return {
        "store": "テング酒場 池袋東口店",
        "period": "2026-03 〜 2026-05",
        "visits": int(df["visit_id"].nunique()),
        "orders": int(df["order_id"].nunique()),
        "items": int(len(df)),
        "note": "全日14-23時（日曜22時まで）・単独客/ランチ定食/対象外メニュー/コース・放題を除外",
        "source": "Supabase poc_ikebukuro_items（PoC専用テーブル）",
    }


@router.get("/poc/available")
def poc_available():
    return {"available": base_table.available()}


@router.post("/poc/analysis/{sid}")
async def run_poc(sid: str):
    if not base_table.available():
        raise HTTPException(status_code=404,
                            detail="PoC用データ（Supabaseテーブル/生CSV/同梱バンドル）が見つかりません。")
    s = sess.get_session(sid)
    if not s:
        raise HTTPException(status_code=404, detail="セッションが見つかりません。")

    df = await run_in_threadpool(base_table.build)
    results = await run_in_threadpool(run_poc_analyses, df)
    meta = _meta(df)
    evidence = lineage.build_evidence_text(df, results, meta)
    sess.update_session(sid, analyses=results, analysis_results=results,
                        poc_meta=meta, poc_evidence=evidence)
    return {"analyses": results, "meta": meta}


@router.get("/poc/evidence/{sid}")
def poc_evidence(sid: str):
    s = sess.get_session(sid)
    text = (s or {}).get("poc_evidence")
    if not text:
        raise HTTPException(status_code=404, detail="先にPoC分析を実行してください。")
    fname = quote("テング池袋PoC_エビデンス.txt")
    return Response(
        content=text.encode("utf-8"),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=poc_evidence.txt; filename*=UTF-8''{fname}"},
    )


@router.get("/poc/categories")
async def poc_categories():
    if not base_table.available():
        raise HTTPException(status_code=404, detail="PoC用データが見つかりません。")
    df = await run_in_threadpool(base_table.build)
    return lineage.category_breakdown(df)


class OverrideReq(BaseModel):
    item_name: str
    category: str


_VALID_CATS = {"ドリンク", "揚げ物", "串", "海鮮", "鍋", "サラダ",
               "ヘビー", "軽いつまみ", "締め", "デザート", "その他"}


@router.post("/poc/categories/override")
async def poc_category_override(req: OverrideReq):
    if req.category not in _VALID_CATS:
        raise HTTPException(status_code=400,
                            detail=f"カテゴリは次から選択: {', '.join(sorted(_VALID_CATS))}")
    try:
        await run_in_threadpool(base_table.set_category, req.item_name, req.category)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))
    return {"ok": True, "item_name": req.item_name, "category": req.category}
