"""Supabase direct table fetch for T1 cloud deployment."""
from __future__ import annotations

import os
from pathlib import Path

import httpx
import pandas as pd
from dotenv import load_dotenv

T1_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = T1_ROOT.parent

load_dotenv(T1_ROOT / "backend" / ".env")
load_dotenv(REPO_ROOT / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY", "")

STORE_ID = 32
START = "2026-03-01T00:00:00"
END = "2026-06-01T00:00:00"
PAGE_SIZE = 1000


def _headers() -> dict[str, str]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL と SUPABASE_SERVICE_KEY または SUPABASE_KEY が未設定です。")
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


def _fetch_table(table: str, params: dict[str, str]) -> list[dict]:
    rows: list[dict] = []
    offset = 0
    with httpx.Client(timeout=httpx.Timeout(connect=10, read=120, write=10, pool=10)) as client:
        while True:
            query = {**params, "limit": str(PAGE_SIZE), "offset": str(offset)}
            response = client.get(
                f"{SUPABASE_URL}/rest/v1/{table}",
                params=query,
                headers=_headers(),
            )
            response.raise_for_status()
            page = response.json()
            if not isinstance(page, list) or not page:
                break
            rows.extend(page)
            if len(page) < PAGE_SIZE:
                break
            offset += PAGE_SIZE
    return rows


def fetch_raw_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fetch order_items and visits for Ikebukuro East PoC period."""
    order_items = _fetch_table(
        "order_items",
        {
            "select": (
                "order_item_id,order_id,visit_id,store_id,item_id,order_seq,line_index,"
                "ordered_at,menu_no,grand_menu_no,item_name,line_type,quantity,unit_price,"
                "subtotal,set_menu_no,set_menu_name,gm_seq_idx"
            ),
            "store_id": f"eq.{STORE_ID}",
            "and": f"(ordered_at.gte.{START},ordered_at.lt.{END})",
        },
    )

    visits = _fetch_table(
        "visits",
        {
            "select": "visit_id,store_id,receipt_no,party_size,visit_start,visit_time,leave_time,total_amount",
            "store_id": f"eq.{STORE_ID}",
            "and": f"(visit_start.gte.{START},visit_start.lt.{END})",
        },
    )

    oi = pd.DataFrame(order_items)
    vs = pd.DataFrame(visits)
    if oi.empty or vs.empty:
        raise RuntimeError("SupabaseからPoC対象データを取得できませんでした。テーブル名/RLS/期間を確認してください。")

    oi["ordered_at"] = _to_naive_datetime(oi["ordered_at"])
    vs["visit_start"] = _to_naive_datetime(vs["visit_start"])
    return oi, vs


def _to_naive_datetime(values) -> pd.Series:
    dt = pd.to_datetime(values, errors="coerce")
    try:
        if getattr(dt.dt, "tz", None) is not None:
            dt = dt.dt.tz_convert("Asia/Tokyo").dt.tz_localize(None)
    except Exception:
        try:
            dt = pd.to_datetime(values, errors="coerce", utc=True).dt.tz_convert("Asia/Tokyo").dt.tz_localize(None)
        except Exception:
            pass
    return dt
