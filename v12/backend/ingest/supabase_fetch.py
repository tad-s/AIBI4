"""Supabase RPC からの売上データ取得（ページネーション + リトライ）。

v8 の data_router のロジックを再利用しやすい形に整理したもの。
"""
from __future__ import annotations

import asyncio
from calendar import monthrange
from datetime import date, timedelta

import httpx

from core.config import settings

_RETRY_STATUS = {502, 503, 504}

DATASET_CONFIG = {
    "izakaya": {"rpc_name": "get_izakaya_sales", "stores_table": "stores"},
    "cafe":    {"rpc_name": "get_cafe_sales",    "stores_table": "cafe_stores"},
    "bakery":  {"rpc_name": "get_bakery_sales",  "stores_table": "bakery_stores"},
    "salon":   {"rpc_name": "get_salon_sales",   "stores_table": "salon_stores"},
}


def _headers() -> dict:
    return {
        "apikey":        settings.SUPABASE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_KEY}",
        "Content-Type":  "application/json",
        "Prefer":        "count=none",
    }


def _week_ranges(start: str, end: str) -> list[tuple[str, str]]:
    s = date.fromisoformat(start)
    e = date.fromisoformat(end)
    out, cur = [], s
    while cur <= e:
        ce = min(cur + timedelta(days=settings.CHUNK_DAYS - 1), e)
        out.append((cur.isoformat(), ce.isoformat()))
        cur = ce + timedelta(days=1)
    return out


def months_to_chunks(months: list[str]) -> list[tuple[str, str]]:
    chunks: list[tuple[str, str]] = []
    for m in sorted(months):
        y, mo = int(m.split("-")[0]), int(m.split("-")[1])
        m_start = f"{y}-{mo:02d}-01"
        m_end = f"{y}-{mo:02d}-{monthrange(y, mo)[1]:02d}"
        chunks.extend(_week_ranges(m_start, m_end))
    return chunks


async def _fetch_chunk(
    client: httpx.AsyncClient, cs: str, ce: str,
    store_ids: list[int] | None, rpc_name: str,
) -> list[dict]:
    params: dict = {"p_start_date": cs, "p_end_date": ce}
    if store_ids:
        params["p_store_ids"] = store_ids
    rows: list[dict] = []
    offset = 0
    while True:
        last_exc: Exception | None = None
        resp = None
        for attempt in range(3):
            try:
                resp = await client.post(
                    f"{settings.SUPABASE_URL}/rest/v1/rpc/{rpc_name}",
                    params={"limit": settings.RPC_PAGE_SIZE, "offset": offset},
                    json=params,
                    headers={**_headers(), "Prefer": "return=representation"},
                )
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
                    await asyncio.sleep(5 * (attempt + 1))
                else:
                    raise
        if last_exc:
            raise last_exc
        page = resp.json()
        if not isinstance(page, list):
            break
        rows.extend(page)
        if len(page) < settings.RPC_PAGE_SIZE:
            break
        offset += settings.RPC_PAGE_SIZE
    return rows


async def fetch_sales(
    dataset: str, months: list[str], store_ids: list[int] | None,
    on_progress=None,
) -> list[dict]:
    """指定データセット・月・店舗の売上明細を全件取得する。

    on_progress(done, total, rows) が渡されれば進捗を通知する。
    """
    cfg = DATASET_CONFIG.get(dataset, DATASET_CONFIG["izakaya"])
    rpc_name = cfg["rpc_name"]
    chunks = months_to_chunks(months)
    total = len(chunks)

    all_rows: list[dict] = []
    done = 0
    sem = asyncio.Semaphore(settings.MAX_WORKERS)
    timeout = httpx.Timeout(connect=10.0, read=settings.CHUNK_TIMEOUT, write=10.0, pool=5.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        async def one(cs: str, ce: str):
            async with sem:
                return await _fetch_chunk(client, cs, ce, store_ids, rpc_name)

        tasks = {asyncio.create_task(one(cs, ce)): (cs, ce) for cs, ce in chunks}
        pending = set(tasks)
        while pending:
            finished, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for t in finished:
                done += 1
                try:
                    all_rows.extend(t.result())
                except Exception:
                    pass
                if on_progress:
                    on_progress(done, total, len(all_rows))
    return all_rows


async def fetch_available_months(dataset: str) -> list[str]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{settings.SUPABASE_URL}/rest/v1/rpc/get_available_months",
            params={"limit": 100},
            json={"p_dataset": dataset},
            headers=_headers(),
        )
        resp.raise_for_status()
        data = resp.json()
    return sorted(r["year_month"] for r in data) if isinstance(data, list) else []


async def fetch_stores(dataset: str) -> list[dict]:
    cfg = DATASET_CONFIG.get(dataset, DATASET_CONFIG["izakaya"])
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{settings.SUPABASE_URL}/rest/v1/{cfg['stores_table']}",
            params={"select": "store_id,store_name"},
            headers=_headers(),
        )
        resp.raise_for_status()
        return resp.json() or []


async def fetch_category_master() -> dict[str, str]:
    """item_category_master テーブル（あれば）を取得。無ければ空 dict。"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{settings.SUPABASE_URL}/rest/v1/item_category_master",
                params={"select": "item_name,category", "limit": 10000},
                headers=_headers(),
            )
        if resp.is_success and isinstance(resp.json(), list):
            return {r["item_name"]: r["category"] for r in resp.json()}
    except Exception:
        pass
    return {}
