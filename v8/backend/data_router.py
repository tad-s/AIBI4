"""
data_router.py — データ取得エンドポイント
GET  /api/months        利用可能な月一覧
GET  /api/stores        店舗一覧
POST /api/sessions      新しいセッション作成
POST /api/fetch         Supabase からデータ取得（SSE でプログレス配信）
GET  /api/sessions/{sid}/summary  取得済みデータのサマリー
"""
import asyncio
import json
import os
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from supabase import create_client

import session as sess
from llm_service import build_data_summary

router = APIRouter()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
CHUNK_DAYS   = 3
MAX_WORKERS  = 4
RPC_PAGE_SIZE = 1000


def _get_sb():
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(status_code=500, detail="SUPABASE_URL / SUPABASE_KEY が未設定です。")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def _week_ranges(start_date: str, end_date: str) -> list[tuple[str, str]]:
    start = date.fromisoformat(start_date)
    end   = date.fromisoformat(end_date)
    chunks, cur = [], start
    while cur <= end:
        chunk_end = min(cur + timedelta(days=CHUNK_DAYS - 1), end)
        chunks.append((cur.isoformat(), chunk_end.isoformat()))
        cur = chunk_end + timedelta(days=1)
    return chunks


def _fetch_chunk(chunk_start: str, chunk_end: str, store_ids: list[int] | None) -> list[dict]:
    """スレッドごとに独立したクライアントで 1 チャンク取得（リトライ付き）。"""
    import time
    _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    params: dict = {"p_start_date": chunk_start, "p_end_date": chunk_end}
    if store_ids:
        params["p_store_ids"] = store_ids

    rows: list[dict] = []
    offset = 0
    while True:
        last_exc = None
        for retry in range(3):
            try:
                result = (
                    _client.rpc("get_izakaya_sales", params)
                    .range(offset, offset + RPC_PAGE_SIZE - 1)
                    .execute()
                )
                last_exc = None
                break
            except Exception as e:
                last_exc = e
                if retry < 2:
                    wait = 10 if "PGRST003" in str(e) else 2 ** (retry + 1)
                    time.sleep(wait)
        if last_exc:
            raise last_exc
        page_rows = result.data or []
        rows.extend(page_rows)
        if len(page_rows) < RPC_PAGE_SIZE:
            break
        offset += RPC_PAGE_SIZE
    return rows


@router.get("/months")
def get_months():
    try:
        sb = _get_sb()
        result = (
            sb.table("visits")
            .select("visit_time")
            .not_.is_("visit_time", "null")
            .limit(3000)
            .execute()
        )
        if not result.data:
            return {"months": []}
        dates = pd.to_datetime(
            [r["visit_time"] for r in result.data], errors="coerce", utc=True
        )
        months = sorted({d.strftime("%Y-%m") for d in dates if pd.notna(d)})
        return {"months": months}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stores")
def get_stores():
    try:
        sb = _get_sb()
        result = sb.table("stores").select("store_id,store_name").execute()
        return {"stores": result.data or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions")
def create_session():
    sid = sess.create_session()
    return {"session_id": sid}


class FetchRequest(BaseModel):
    session_id: str
    months: list[str]        # ["2024-09", "2024-10"]
    store_ids: list[int] | None = None


@router.post("/fetch")
async def fetch_data(req: FetchRequest):
    """SSE でプログレスを配信しながら Supabase からデータを取得する。"""
    if not sess.get_session(req.session_id):
        raise HTTPException(status_code=404, detail="セッションが見つかりません。")

    from calendar import monthrange
    starts, ends = [], []
    for m in req.months:
        y, mo = int(m.split("-")[0]), int(m.split("-")[1])
        starts.append(f"{y}-{mo:02d}-01")
        ends.append(f"{y}-{mo:02d}-{monthrange(y, mo)[1]:02d}")
    start_date, end_date = min(starts), max(ends)
    chunks = _week_ranges(start_date, end_date)
    total_chunks = len(chunks)

    async def event_stream():
        all_rows: list[dict] = []
        done = 0
        loop = asyncio.get_event_loop()

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_map = {
                executor.submit(_fetch_chunk, cs, ce, req.store_ids): (cs, ce)
                for cs, ce in chunks
            }
            for future in as_completed(future_map):
                try:
                    chunk_rows = await loop.run_in_executor(None, future.result)
                    all_rows.extend(chunk_rows)
                except Exception as e:
                    yield f"data: {json.dumps({'type':'error','message':str(e)})}\n\n"
                    continue

                done += 1
                pct = round(done / total_chunks * 100)
                yield f"data: {json.dumps({'type':'progress','done':done,'total':total_chunks,'rows':len(all_rows),'pct':pct})}\n\n"
                await asyncio.sleep(0)  # allow event loop to flush

        if all_rows:
            df = _build_df(all_rows)
            summary = build_data_summary(df)
            sess.update_session(req.session_id, df=df, summary_text=summary, chat_history=[])
            yield f"data: {json.dumps({'type':'done','rows':len(df),'columns':list(df.columns)})}\n\n"
        else:
            yield f"data: {json.dumps({'type':'done','rows':0,'columns':[]})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _build_df(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["unit_price"] = pd.to_numeric(df.get("unit_price", 0), errors="coerce").fillna(0)
    df["quantity"]   = pd.to_numeric(df.get("quantity",   0), errors="coerce").fillna(0)
    if "party_size" in df.columns:
        df["party_size"] = pd.to_numeric(df["party_size"], errors="coerce").fillna(0).astype(int)
    for col in ["visit_time", "leave_time", "order_time"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)
            try:
                df[col] = df[col].dt.tz_convert("Asia/Tokyo")
            except Exception:
                pass

    df["_line_total"] = df["unit_price"] * df["quantity"]
    visit_total = df.groupby("receipt_no")["_line_total"].sum().rename("合計金額(税込)")
    df = df.join(visit_total, on="receipt_no")

    df = df.rename(columns={
        "receipt_no":     "伝票番号",
        "order_time":     "注文日時",
        "visit_time":     "来店時間",
        "leave_time":     "退店時間",
        "party_size":     "人数",
        "customer_layer": "客層",
        "store_name":     "店舗名",
        "shop_code":      "店舗コード",
        "item_name_raw":  "商品名",
        "quantity":       "数量",
        "unit_price":     "単価",
    })
    df = df.drop(columns=["_line_total"], errors="ignore")
    return df.reset_index(drop=True)


@router.get("/sessions/{sid}/summary")
def get_summary(sid: str):
    s = sess.get_session(sid)
    if not s:
        raise HTTPException(status_code=404, detail="セッションが見つかりません。")
    df = s.get("df")
    if df is None:
        return {"has_data": False}
    return {
        "has_data": True,
        "rows": len(df),
        "columns": list(df.columns),
        "stores": df["店舗名"].dropna().unique().tolist() if "店舗名" in df.columns else [],
        "summary_text": s.get("summary_text", ""),
    }
