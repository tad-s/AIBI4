"""PoC基礎テーブル構築（生CSV → 除外適用済みの order 粒度 df）。

現行RPC(get_izakaya_sales)は DISTINCT ON でオーダー粒度を潰すため、同時/連続
オーダー分析には使えない。ここでは生テーブル(order_items/orders/visits)を直接結合し、
要件の除外を適用した明細テーブルを構築する。1来店ID = visit_id（源泉UUID）。

結果はプロセス内キャッシュ（データは静的）。
"""
from __future__ import annotations

import csv
import os

import httpx
import pandas as pd

from poc.classify import classify, set_master
from poc.overrides import build_master

# 本命: Supabase の PoC専用テーブル（要件どおり別テーブルを参照）。
# anon キーで読める（RLS でSELECT許可済み）。列は基礎テーブルと同一。
_SUPA_URL = os.getenv("SUPABASE_URL", "")
_SUPA_KEY = os.getenv("SUPABASE_KEY", "")
_SUPA_SVC = os.getenv("SUPABASE_SERVICE_KEY", "")   # カテゴリ編集(書込)用
_TABLE = "poc_ikebukuro_items"
_PAGE = 1000


def set_category(item_name: str, category: str) -> None:
    """PoC専用テーブルの item_name のカテゴリを更新（原本は不変）。fd も派生更新。

    書込には service key が必要（anon は RLS で SELECT のみ）。更新後はキャッシュ破棄。
    """
    if not (_SUPA_URL and _SUPA_SVC):
        raise RuntimeError("SUPABASE_SERVICE_KEY が未設定のためカテゴリ編集できません。")
    fd = "ドリンク" if category == "ドリンク" else "フード"
    hdr = {"apikey": _SUPA_SVC, "Authorization": f"Bearer {_SUPA_SVC}",
           "Content-Type": "application/json", "Prefer": "return=minimal"}
    with httpx.Client(timeout=60) as c:
        r = c.patch(f"{_SUPA_URL}/rest/v1/{_TABLE}", headers=hdr,
                    params={"item_name": f"eq.{item_name}"},
                    json={"category": category, "fd": fd})
        r.raise_for_status()
    global _CACHE
    _CACHE = None   # 次回 build() で最新を再取得

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
    return bool(_SUPA_URL and _SUPA_KEY) or os.path.isdir(_DATA) or os.path.exists(_BUNDLE)


def _coerce(df: pd.DataFrame) -> pd.DataFrame:
    for col in ["party_size", "order_seq", "line_index", "quantity", "unit_price"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "party_size" in df.columns:
        df["party_size"] = df["party_size"].fillna(0).astype(int)
    return df


def _load_from_supabase() -> pd.DataFrame:
    """PoC専用テーブル poc_ikebukuro_items を anon キーで全件取得（1000行ページ）。"""
    cols = ("visit_id,store_id,receipt_no,party_size,visit_start,order_id,order_seq,"
            "line_index,ordered_at,item_name,category,fd,quantity,unit_price")
    hdr = {"apikey": _SUPA_KEY, "Authorization": f"Bearer {_SUPA_KEY}"}
    rows: list[dict] = []
    off = 0
    with httpx.Client(timeout=60) as c:
        while True:
            r = c.get(f"{_SUPA_URL}/rest/v1/{_TABLE}",
                      headers={**hdr, "Range": f"{off}-{off + _PAGE - 1}"},
                      params={"select": cols})
            r.raise_for_status()
            batch = r.json()
            rows += batch
            if len(batch) < _PAGE:
                break
            off += _PAGE
    return _coerce(pd.DataFrame(rows))


def _load_bundle() -> pd.DataFrame:
    return _coerce(pd.read_csv(_BUNDLE, dtype=str, compression="gzip"))


def build(force: bool = False) -> pd.DataFrame:
    global _CACHE
    if _CACHE is not None and not force:
        return _CACHE

    # 本命: Supabase の PoC専用テーブルを参照（要件どおり別テーブル）
    if _SUPA_URL and _SUPA_KEY:
        try:
            df = _load_from_supabase()
            if len(df):
                _CACHE = df
                return _CACHE
        except Exception:
            pass  # 取得失敗時はローカル(生CSV/バンドル)へフォールバック

    # 生CSVが無い本番では同梱バンドルを読む
    if not os.path.isdir(_DATA):
        if os.path.exists(_BUNDLE):
            _CACHE = _load_bundle()
            return _CACHE
        raise FileNotFoundError("PoC用データ（Supabaseテーブル/生CSV/同梱バンドル）が見つかりません。")

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
