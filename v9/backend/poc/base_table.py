"""PoC基礎テーブル構築（生CSV → 除外適用済みの order 粒度 df）。

現行RPC(get_izakaya_sales)は DISTINCT ON でオーダー粒度を潰すため、同時/連続
オーダー分析には使えない。ここでは生テーブル(order_items/orders/visits)を直接結合し、
要件の除外を適用した明細テーブルを構築する。1来店ID = visit_id（源泉UUID）。

結果はプロセス内キャッシュ（データは静的）。
"""
from __future__ import annotations

import csv
import os

import pandas as pd

from poc.classify import classify, set_master
from poc.overrides import build_master

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_DATA = os.path.join(_ROOT, "data", "池袋東口店")
_ETC = os.path.join(_ROOT, "etc")

PERIOD_START = pd.Timestamp("2026-03-01")
PERIOD_END = pd.Timestamp("2026-06-01")
OPEN_HOUR = 14
CLOSE_DEFAULT = 23
CLOSE_SUNDAY = 22
_COURSE_KW = ["お好みコース", "飲み放題", "放題", "お好み宴会", "宴会コース"]

# 本番(Railway)には生CSV(data/池袋東口店)が無いため、除外適用済みの軽量スナップショットを同梱する。
# 開発時(生CSVあり)は毎回CSVから再構築し、このバンドルも更新する。
_BUNDLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "poc_base.csv.gz")

_CACHE: pd.DataFrame | None = None


def _exclusion_names() -> set[str]:
    names: set[str] = set()
    p = os.path.join(_ETC, "池袋東口店_定食メニュー.txt")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if s and not s.startswith("＜") and not s.startswith("・"):
                    names.add(s)
    c = os.path.join(_ETC, "分析対象外メニュー.csv")
    if os.path.exists(c):
        with open(c, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                nm = (row.get("item_name") or "").strip()
                if nm:
                    names.add(nm)
    return names


def available() -> bool:
    return os.path.isdir(_DATA) or os.path.exists(_BUNDLE)


def _load_bundle() -> pd.DataFrame:
    df = pd.read_csv(_BUNDLE, dtype=str, compression="gzip")
    for col in ["party_size", "order_seq", "quantity", "unit_price"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["party_size"] = df["party_size"].fillna(0).astype(int)
    return df


def build(force: bool = False) -> pd.DataFrame:
    global _CACHE
    if _CACHE is not None and not force:
        return _CACHE

    # 生CSVが無い本番では同梱バンドルを読む
    if not os.path.isdir(_DATA):
        if os.path.exists(_BUNDLE):
            _CACHE = _load_bundle()
            return _CACHE
        raise FileNotFoundError("PoC用データ（生CSVも同梱バンドルも）が見つかりません。")

    set_master(build_master(os.path.join(_ETC, "item_category_master.sql")))

    oi = pd.read_csv(os.path.join(_DATA, "池袋東口店_order_items.csv"), dtype=str)
    vs = pd.read_csv(os.path.join(_DATA, "池袋東口店_visits.csv"), dtype=str)
    oi["quantity"] = pd.to_numeric(oi["quantity"], errors="coerce").fillna(0)
    oi["unit_price"] = pd.to_numeric(oi["unit_price"], errors="coerce").fillna(0)
    oi["order_seq"] = pd.to_numeric(oi["order_seq"], errors="coerce")
    oi["ordered_at"] = pd.to_datetime(oi["ordered_at"], errors="coerce")
    vs["party_size"] = pd.to_numeric(vs["party_size"], errors="coerce").fillna(0).astype(int)
    vs["visit_start"] = pd.to_datetime(vs["visit_start"], errors="coerce")

    df = oi.merge(
        vs[["visit_id", "store_id", "receipt_no", "party_size", "visit_start"]],
        on=["visit_id", "store_id"], how="inner",
    )
    df = df[df["line_type"] == "M"]                                   # 実注文品のみ（S=無料オプション除外）
    df = df[(df["ordered_at"] >= PERIOD_START) & (df["ordered_at"] < PERIOD_END)]
    hour = df["ordered_at"].dt.hour
    dow = df["ordered_at"].dt.dayofweek
    close = dow.map(lambda d: CLOSE_SUNDAY if d == 6 else CLOSE_DEFAULT)
    df = df[(hour >= OPEN_HOUR) & (hour < close)]                     # 14-23時（日22時）
    df = df[~df["item_name"].isin(_exclusion_names())]                # 定食+対象外CSV
    df = df[~df["item_name"].map(lambda x: any(k in str(x) for k in _COURSE_KW))]

    df = df.copy()
    df["category"] = df["item_name"].map(classify)
    df = df[df["category"] != "除外"]
    df["fd"] = df["category"].map(lambda c: "ドリンク" if c == "ドリンク" else "フード")

    out = df[[
        "visit_id", "store_id", "receipt_no", "party_size", "visit_start",
        "order_id", "order_seq", "line_index", "ordered_at",
        "item_name", "category", "fd", "quantity", "unit_price",
    ]].reset_index(drop=True)

    # 本番同梱用の軽量バンドルを更新（除外適用済みスナップショット）
    try:
        os.makedirs(os.path.dirname(_BUNDLE), exist_ok=True)
        out.to_csv(_BUNDLE, index=False, compression="gzip")
    except Exception:
        pass

    _CACHE = out
    return out
