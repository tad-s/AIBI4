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

import httpx
import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import session as sess
from llm_service import build_data_summary

router = APIRouter()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
CHUNK_DAYS    = 3
MAX_WORKERS   = 1          # Supabase 無料プランは同時接続を絞る
RPC_PAGE_SIZE = 1000
CHUNK_TIMEOUT = 120.0      # 1チャンク最大120秒（httpx レベルで切断）
_RETRY_STATUS = {502, 503, 504}  # 一時的なサーバーエラーはリトライ


def _sb_headers() -> dict:
    return {
        "apikey":        SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type":  "application/json",
        "Prefer":        "count=none",
    }


def _week_ranges(start_date: str, end_date: str) -> list[tuple[str, str]]:
    start = date.fromisoformat(start_date)
    end   = date.fromisoformat(end_date)
    chunks, cur = [], start
    while cur <= end:
        chunk_end = min(cur + timedelta(days=CHUNK_DAYS - 1), end)
        chunks.append((cur.isoformat(), chunk_end.isoformat()))
        cur = chunk_end + timedelta(days=1)
    return chunks


async def _fetch_chunk_async(
    client: httpx.AsyncClient,
    chunk_start: str,
    chunk_end: str,
    store_ids: list[int] | None,
) -> list[dict]:
    """httpx.AsyncClient で 1 チャンクを非同期取得（ページネーション + リトライ付き）。"""
    params: dict = {"p_start_date": chunk_start, "p_end_date": chunk_end}
    if store_ids:
        params["p_store_ids"] = store_ids

    rows: list[dict] = []
    offset = 0
    while True:
        # リトライ最大3回
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                resp = await client.post(
                    f"{SUPABASE_URL}/rest/v1/rpc/get_izakaya_sales",
                    json=params,
                    headers={
                        **_sb_headers(),
                        "Range": f"{offset}-{offset + RPC_PAGE_SIZE - 1}",
                        "Prefer": "return=representation",
                    },
                )
                # 416 = データなし / ページ外
                if resp.status_code == 416:
                    return rows
                resp.raise_for_status()
                last_exc = None
                break
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                last_exc = e
                if attempt < 2:
                    await asyncio.sleep(3 ** attempt)
            except httpx.HTTPStatusError as e:
                if e.response.status_code in _RETRY_STATUS and attempt < 2:
                    last_exc = e
                    await asyncio.sleep(5 * (attempt + 1))  # 5s, 10s
                else:
                    raise
        if last_exc:
            raise last_exc

        page = resp.json()
        if not isinstance(page, list):
            break
        rows.extend(page)
        if len(page) < RPC_PAGE_SIZE:
            break
        offset += RPC_PAGE_SIZE
    return rows


@router.get("/months")
async def get_months():
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/visits",
                params={"select": "visit_time", "visit_time": "not.is.null", "limit": "3000"},
                headers=_sb_headers(),
            )
            resp.raise_for_status()
            data = resp.json()
        if not data:
            return {"months": []}
        dates = pd.to_datetime(
            [r["visit_time"] for r in data], errors="coerce", utc=True
        )
        months = sorted({d.strftime("%Y-%m") for d in dates if pd.notna(d)})
        return {"months": months}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stores")
async def get_stores():
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/stores",
                params={"select": "store_id,store_name"},
                headers=_sb_headers(),
            )
            resp.raise_for_status()
            return {"stores": resp.json() or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions")
def create_session():
    sid = sess.create_session()
    return {"session_id": sid}


class FetchRequest(BaseModel):
    session_id: str
    months: list[str]
    store_ids: list[int] | None = None


@router.post("/fetch")
async def fetch_data(req: FetchRequest):
    """SSE でプログレスを配信しながら Supabase からデータを取得する。"""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(status_code=500, detail="SUPABASE_URL / SUPABASE_KEY が未設定です。")
    if not sess.get_session(req.session_id):
        raise HTTPException(status_code=404, detail="セッションが見つかりません。")

    from calendar import monthrange
    chunks: list[tuple[str, str]] = []
    chunk_month: dict[tuple[str, str], str] = {}
    for m in sorted(req.months):
        y, mo = int(m.split("-")[0]), int(m.split("-")[1])
        m_start = f"{y}-{mo:02d}-01"
        m_end   = f"{y}-{mo:02d}-{monthrange(y, mo)[1]:02d}"
        for cs, ce in _week_ranges(m_start, m_end):
            chunks.append((cs, ce))
            chunk_month[(cs, ce)] = m
    total_chunks = len(chunks)

    async def event_stream():
        all_rows: list[dict] = []
        done = 0
        sem = asyncio.Semaphore(MAX_WORKERS)

        # httpx.AsyncClient を共有（接続プール再利用）
        timeout = httpx.Timeout(connect=10.0, read=CHUNK_TIMEOUT, write=10.0, pool=5.0)
        async with httpx.AsyncClient(timeout=timeout) as client:

            async def fetch_one(cs: str, ce: str) -> tuple[str, str, list[dict]]:
                async with sem:
                    rows = await _fetch_chunk_async(client, cs, ce, req.store_ids)
                    return cs, ce, rows

            task_map: dict[asyncio.Task, tuple[str, str]] = {
                asyncio.create_task(fetch_one(cs, ce)): (cs, ce)
                for cs, ce in chunks
            }
            pending = set(task_map.keys())

            while pending:
                finished, pending = await asyncio.wait(
                    pending, return_when=asyncio.FIRST_COMPLETED
                )
                for task in finished:
                    cs, ce = task_map[task]
                    done += 1
                    try:
                        _, _, chunk_rows = task.result()
                        all_rows.extend(chunk_rows)
                    except Exception as e:
                        yield f"data: {json.dumps({'type':'error','message':f'{cs}〜{ce}: {e}'})}\n\n"

                    month_label = chunk_month.get((cs, ce), cs[:7])
                    pct = round(done / total_chunks * 100)
                    yield f"data: {json.dumps({'type':'progress','done':done,'total':total_chunks,'rows':len(all_rows),'pct':pct,'month':month_label})}\n\n"

        if all_rows:
            yield f"data: {json.dumps({'type':'processing','message':'データを整形中…'})}\n\n"
            loop = asyncio.get_running_loop()
            df = await loop.run_in_executor(None, _build_df, all_rows)

            yield f"data: {json.dumps({'type':'processing','message':'LLM サマリーを生成中…'})}\n\n"
            summary = await loop.run_in_executor(None, build_data_summary, df)

            sess.update_session(req.session_id, df=df, summary_text=summary, chat_history=[])
            yield f"data: {json.dumps({'type':'done','rows':len(df),'columns':list(df.columns)})}\n\n"
        else:
            yield f"data: {json.dumps({'type':'done','rows':0,'columns':[]})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
