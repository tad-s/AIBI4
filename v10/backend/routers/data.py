"""セッション作成・データ投入（Supabase → DuckDB, SSE 進捗配信）。"""
import asyncio
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.config import settings
from core.duck import store
from ingest import categories
from ingest.supabase_fetch import fetch_category_master, fetch_sales
from ingest.transform import build_items_df

router = APIRouter(prefix="/api")


class CreateSessionReq(BaseModel):
    dataset: str = "izakaya"


class LoadReq(BaseModel):
    session_id: str
    dataset: str = "izakaya"
    months: list[str]
    store_ids: list[int] | None = None


@router.post("/sessions")
def create_session(req: CreateSessionReq):
    sid = store.create(req.dataset)
    return {"session_id": sid}


@router.post("/load")
async def load(req: LoadReq):
    if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
        raise HTTPException(status_code=500, detail="SUPABASE_URL / SUPABASE_KEY が未設定です。")
    session = store.get(req.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="セッションが見つかりません。")

    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def on_progress(done: int, total: int, rows: int):
        pct = round(done / total * 100) if total else 100
        loop.call_soon_threadsafe(
            queue.put_nowait,
            {"type": "progress", "done": done, "total": total, "rows": rows, "pct": pct},
        )

    async def worker():
        try:
            # カテゴリマスタ（あれば）を反映
            master = await fetch_category_master()
            if master:
                categories.set_master(master)

            rows = await fetch_sales(req.dataset, req.months, req.store_ids, on_progress)
            if not rows:
                await queue.put({"type": "done", "meta": {"item_rows": 0, "order_rows": 0}})
                return
            await queue.put({"type": "processing", "message": "DuckDB に投入中…"})
            items_df = await loop.run_in_executor(None, build_items_df, rows)
            await loop.run_in_executor(None, session.load, items_df)
            await queue.put({"type": "done", "meta": session.meta})
        except Exception as e:
            await queue.put({"type": "error", "message": str(e)})
        finally:
            await queue.put(None)

    async def event_stream():
        task = asyncio.create_task(worker())
        try:
            while True:
                ev = await queue.get()
                if ev is None:
                    break
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/sessions/{sid}/meta")
def session_meta(sid: str):
    session = store.get(sid)
    if session is None:
        raise HTTPException(status_code=404, detail="セッションが見つかりません。")
    return {"dataset": session.dataset, "meta": session.meta}
