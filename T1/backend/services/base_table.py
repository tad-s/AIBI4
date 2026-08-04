"""池袋東口店 PoC の基礎テーブル構築。"""
from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

from services.categories import classify
from services.supabase_source import fetch_raw_frames

T1_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = T1_ROOT.parent
RAW_DIR = REPO_ROOT / "data" / "池袋東口店"
CONFIG_DIR = T1_ROOT / "config"
ETC_DIR = REPO_ROOT / "etc"
T1_DATA = T1_ROOT / "data"
BASE_CSV = T1_DATA / "t1_poc_base.csv"
LEGACY_PARQUET = REPO_ROOT / "poc" / "data" / "poc_base.parquet"

PERIOD_START = pd.Timestamp("2026-03-01")
PERIOD_END = pd.Timestamp("2026-06-01")
OPEN_HOUR = 14
CLOSE_HOUR_DEFAULT = 23
CLOSE_HOUR_SUNDAY = 22
COURSE_KEYWORDS = ["お好みコース", "飲み放題", "放題", "お好み宴会", "宴会コース"]


def load_exclusion_names() -> set[str]:
    names: set[str] = set()
    lunch_file = CONFIG_DIR / "池袋東口店_定食メニュー.txt"
    if not lunch_file.exists():
        lunch_file = ETC_DIR / "池袋東口店_定食メニュー.txt"
    if lunch_file.exists():
        for line in lunch_file.read_text(encoding="utf-8").splitlines():
            item = line.strip()
            if item and not item.startswith("＜") and not item.startswith("・"):
                names.add(item)

    excluded_csv = CONFIG_DIR / "分析対象外メニュー.csv"
    if not excluded_csv.exists():
        excluded_csv = ETC_DIR / "分析対象外メニュー.csv"
    if excluded_csv.exists():
        with excluded_csv.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                item = (row.get("item_name") or "").strip()
                if item:
                    names.add(item)
    return names


def is_course_item(name: str) -> bool:
    return any(keyword in str(name) for keyword in COURSE_KEYWORDS)


def build_base_table(force: bool = False) -> tuple[pd.DataFrame, list[dict]]:
    if BASE_CSV.exists() and not force:
        df = read_base_table()
        return df, [{"step": "既存T1基礎テーブル読込", "rows": len(df), "visits": df["visit_id"].nunique()}]

    order_items_path = RAW_DIR / "池袋東口店_order_items.csv"
    visits_path = RAW_DIR / "池袋東口店_visits.csv"
    source_label = "ローカルCSV"
    if order_items_path.exists() and visits_path.exists():
        oi = pd.read_csv(order_items_path, dtype=str)
        visits = pd.read_csv(visits_path, dtype=str)
    elif LEGACY_PARQUET.exists():
        df = pd.read_parquet(LEGACY_PARQUET)
        T1_DATA.mkdir(parents=True, exist_ok=True)
        df.to_csv(BASE_CSV, index=False, encoding="utf-8-sig")
        return df, [{"step": "既存poc_base.parquetからT1へコピー", "rows": len(df), "visits": df["visit_id"].nunique()}]
    else:
        oi, visits = fetch_raw_frames()
        source_label = "Supabase直接取得"
    oi["quantity"] = pd.to_numeric(oi["quantity"], errors="coerce").fillna(0)
    oi["unit_price"] = pd.to_numeric(oi["unit_price"], errors="coerce").fillna(0)
    oi["order_seq"] = pd.to_numeric(oi["order_seq"], errors="coerce")
    oi["line_index"] = pd.to_numeric(oi["line_index"], errors="coerce")
    oi["ordered_at"] = _to_naive_datetime(oi["ordered_at"])
    visits["party_size"] = pd.to_numeric(visits["party_size"], errors="coerce").fillna(0).astype(int)
    visits["visit_start"] = _to_naive_datetime(visits["visit_start"])

    funnel: list[dict] = []

    def log(step: str, frame: pd.DataFrame):
        funnel.append({"step": step, "rows": int(len(frame)), "visits": int(frame["visit_id"].nunique())})

    log(f"生 order_items ({source_label})", oi)
    df = oi.merge(
        visits[["visit_id", "store_id", "receipt_no", "party_size", "visit_start"]],
        on=["visit_id", "store_id"],
        how="inner",
    )
    log("visits結合後", df)

    df = df[df["line_type"] == "M"].copy()
    log("M行のみ", df)

    df = df[(df["ordered_at"] >= PERIOD_START) & (df["ordered_at"] < PERIOD_END)]
    log("期間 2026年3-5月", df)

    hour = df["ordered_at"].dt.hour
    dow = df["ordered_at"].dt.dayofweek
    close_hour = dow.map(lambda day: CLOSE_HOUR_SUNDAY if day == 6 else CLOSE_HOUR_DEFAULT)
    df = df[(hour >= OPEN_HOUR) & (hour < close_hour)]
    log("対象時間 14時-閉店", df)

    exclusions = load_exclusion_names()
    df = df[~df["item_name"].isin(exclusions)]
    log("定食+対象外CSV除外", df)

    df = df[~df["item_name"].map(is_course_item)]
    log("コース/飲み放題除外", df)

    df["category"] = df["item_name"].map(classify)
    df = df[df["category"] != "除外"].copy()
    log("分類上の除外カテゴリ除外", df)

    df["fd"] = df["category"].map(lambda c: "ドリンク" if c == "ドリンク" else "フード")
    df["line_total"] = df["quantity"] * df["unit_price"]
    out = df[[
        "visit_id", "store_id", "receipt_no", "party_size", "visit_start",
        "order_id", "order_seq", "line_index", "ordered_at",
        "item_name", "category", "fd", "quantity", "unit_price", "line_total",
    ]].reset_index(drop=True)

    T1_DATA.mkdir(parents=True, exist_ok=True)
    out.to_csv(BASE_CSV, index=False, encoding="utf-8-sig")
    return out, funnel


def read_base_table() -> pd.DataFrame:
    if BASE_CSV.exists():
        df = pd.read_csv(BASE_CSV)
    elif LEGACY_PARQUET.exists():
        df = pd.read_parquet(LEGACY_PARQUET)
    else:
        df, _ = build_base_table(force=True)
        return df
    df["ordered_at"] = _to_naive_datetime(df["ordered_at"])
    df["visit_start"] = _to_naive_datetime(df["visit_start"])
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(0)
    df["unit_price"] = pd.to_numeric(df["unit_price"], errors="coerce").fillna(0)
    df["line_total"] = pd.to_numeric(df.get("line_total", df["quantity"] * df["unit_price"]), errors="coerce").fillna(0)
    df["party_size"] = pd.to_numeric(df["party_size"], errors="coerce").fillna(0).astype(int)
    df["order_seq"] = pd.to_numeric(df["order_seq"], errors="coerce")
    return df


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
