"""テング池袋東口店 PoC 分析エンドポイント。

POST /api/poc/analysis/{sid}      … 4分析(+カテゴリ版)を実行して返す
GET  /api/poc/evidence/{sid}      … データ来歴（原本CSV→変換→集計）テキストをDL
GET  /api/poc/categories          … カテゴリ内訳（ドリルダウン用）
POST /api/poc/categories/override … 商品のカテゴリを編集（PoC専用テーブルを更新・原本不変）
"""
from urllib.parse import quote

import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel

import session as sess
from llm_service import build_data_summary
from poc import base_table, lineage
from poc.analyses import run_poc_analyses

router = APIRouter()


def _to_chat_df(df: pd.DataFrame) -> pd.DataFrame:
    """PoC df(英語カラム) → チャット互換df(日本語カラム)。

    既存チャットのプロンプト/レシピ（来店ID・来店時間・人数・商品名・合計金額(税込)）が
    そのまま使えるようにする。PoC固有の列（カテゴリ・フードドリンク・オーダーID/順）も残す。
    来店ID = visit_id（源泉UUID）。時刻はJST naive に統一。
    """
    d = df.copy()
    qty = pd.to_numeric(d["quantity"], errors="coerce").fillna(0)
    price = pd.to_numeric(d["unit_price"], errors="coerce").fillna(0)
    line = qty * price

    def jst(col):
        s = pd.to_datetime(d[col], errors="coerce", utc=True)
        try:
            s = s.dt.tz_convert("Asia/Tokyo")
        except Exception:
            pass
        return s.dt.tz_localize(None)

    out = pd.DataFrame({
        "来店ID":   d["visit_id"],
        "伝票番号": d["receipt_no"],
        "来店時間": jst("visit_start"),
        "注文日時": jst("ordered_at"),
        "人数":     pd.to_numeric(d["party_size"], errors="coerce"),
        "店舗名":   "テング池袋東口店",
        "商品名":   d["item_name"],
        "数量":     qty,
        "単価":     price,
        "カテゴリ": d["category"],
        "フードドリンク": d["fd"],
        "オーダーID": d["order_id"],
        "オーダー順": pd.to_numeric(d["order_seq"], errors="coerce"),
    })
    out["合計金額(税込)"] = pd.Series(line).groupby(d["visit_id"].values).transform("sum").values
    return out.reset_index(drop=True)


_POC_CHAT_NOTE = (
    "【重要】これはテング酒場 池袋東口店のPoC専用データ（2026-03〜05・全日14-23時/日曜22時まで・"
    "単独客/ランチ定食/対象外メニュー/コース・放題を除外）です。"
    "来店・人数・客単価は列『来店ID』で一意化して数えること。"
    "追加列: カテゴリ(商品分類), フードドリンク(ドリンク/フード), オーダーID(同時注文の単位), "
    "オーダー順(来店内の注文順・連続注文の判定に使用)。\n"
)


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

    # PoCデータをチャットの対象データとして設定（PoC分析後もチャットで分析できるように）
    chat_df = await run_in_threadpool(_to_chat_df, df)
    summary = _POC_CHAT_NOTE + await run_in_threadpool(build_data_summary, chat_df)
    sess.update_session(sid, analyses=results, analysis_results=results,
                        poc_meta=meta, poc_evidence=evidence,
                        df=chat_df, summary_text=summary, chat_history=[],
                        pending_analysis=None)
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
