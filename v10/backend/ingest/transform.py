"""Supabase RPC の生行 → DuckDB 投入用のクリーンな商品明細 DataFrame。"""
from __future__ import annotations

import pandas as pd

from ingest.categories import classify

# RPC が返す天気列 → 内部列名
_WEATHER_MAP = {
    "temperature_2m_max":  "temp_max",
    "temperature_2m_min":  "temp_min",
    "temperature_2m_mean": "temp_mean",
    "precipitation_sum":   "precip",
    "weather_label":       "weather_label",
}


def _to_jst_naive(s: pd.Series) -> pd.Series:
    dt = pd.to_datetime(s, errors="coerce", utc=True)
    try:
        dt = dt.dt.tz_convert("Asia/Tokyo")
    except Exception:
        pass
    return dt.dt.tz_localize(None)


def build_items_df(rows: list[dict]) -> pd.DataFrame:
    """明細行を分析用の item 粒度 DataFrame に整形する。"""
    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df["unit_price"] = pd.to_numeric(df.get("unit_price", 0), errors="coerce").fillna(0)
    df["quantity"] = pd.to_numeric(df.get("quantity", 0), errors="coerce").fillna(0)
    df["party_size"] = pd.to_numeric(df.get("party_size", 0), errors="coerce").fillna(0).astype(int)

    for src in ["visit_time", "leave_time", "order_time"]:
        df[src] = _to_jst_naive(df[src]) if src in df.columns else pd.NaT

    df["line_total"] = df["unit_price"] * df["quantity"]

    out = pd.DataFrame({
        "store_name":     df.get("store_name"),
        "shop_code":      df.get("shop_code"),
        "receipt_no":     df.get("receipt_no").astype(str),
        "visit_time":     df["visit_time"],
        "leave_time":     df["leave_time"],
        "order_time":     df["order_time"],
        "party_size":     df["party_size"],
        "customer_layer": df.get("customer_layer"),
        "item_name":      df.get("item_name_raw"),
        "quantity":       df["quantity"],
        "unit_price":     df["unit_price"],
        "line_total":     df["line_total"],
    })

    # 天気列
    for src, dst in _WEATHER_MAP.items():
        if src in df.columns:
            out[dst] = pd.to_numeric(df[src], errors="coerce") if dst != "weather_label" else df[src]
        else:
            out[dst] = None

    # 複合キー・カテゴリ
    out["visit_key"] = (
        out["visit_time"].dt.strftime("%Y%m%d%H%M%S").fillna("?") + "_" + out["receipt_no"]
    )
    out["category"] = out["item_name"].map(classify)

    # システム項目（除外カテゴリ）を落とす
    out = out[out["category"] != "除外"].copy()

    # 派生時間列
    out["hour"] = out["visit_time"].dt.hour
    out["dow"] = out["visit_time"].dt.dayofweek  # 0=月
    out["date"] = out["visit_time"].dt.date.astype(str)
    out["year_month"] = out["visit_time"].dt.strftime("%Y-%m")

    return out.reset_index(drop=True)
