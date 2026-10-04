"""池袋東口PoC 追加データ(2026-09)を poc_ikebukuro_items へ投入する。

既存3-5月と同じ加工（M行/期間/14-23時(日22)/定食・対象外/コース/classify分類(除外落とし)
/宴・FD除外）を適用し、customer_layer・customer_layer2 を保持して投入する。
store_id は元データのまま(=5)。時刻は JST(+09:00) で投入し Postgres が UTC へ正規化。

前提: 先に ALTER で customer_layer / customer_layer2 列を追加しておくこと。
実行: cd v9/backend && ../../v8/backend/.venv/Scripts/python.exe load_202609.py
"""
import os
import sys

import httpx
import pandas as pd
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

import poc.base_table as BT
from poc.classify import classify, set_master
from poc.overrides import build_master

URL = os.getenv("SUPABASE_URL")
SVC = os.getenv("SUPABASE_SERVICE_KEY")
KEY = os.getenv("SUPABASE_KEY")
TABLE = "poc_ikebukuro_items"
SRC = os.path.join(os.path.dirname(__file__), "..", "..",
                   "data", "池袋東口店", "池袋東口店_追加データ202609")
PERIOD_START = pd.Timestamp("2026-09-01")
PERIOD_END = pd.Timestamp("2026-10-01")
NEW_COLS = ["customer_layer", "customer_layer2"]

if not (URL and SVC):
    sys.exit("SUPABASE_URL / SUPABASE_SERVICE_KEY が未設定です（.env を確認）。")


def _check_alter() -> None:
    """2列が追加済みか確認（未追加なら中止）。"""
    r = httpx.get(f"{URL}/rest/v1/{TABLE}",
                  headers={"apikey": KEY, "Authorization": f"Bearer {KEY}"},
                  params={"limit": 1})
    r.raise_for_status()
    cols = set(r.json()[0].keys())
    missing = [c for c in NEW_COLS if c not in cols]
    if missing:
        sys.exit(f"列 {missing} が未追加です。先に ALTER TABLE を実行してください。")
    print(f"ALTER確認OK: {NEW_COLS} は存在します。")


def _idempotency() -> None:
    """既に store_id=5（9月分）が投入済みでないか確認（二重投入防止）。"""
    r = httpx.get(f"{URL}/rest/v1/{TABLE}",
                  headers={"apikey": KEY, "Authorization": f"Bearer {KEY}",
                           "Prefer": "count=exact", "Range": "0-0"},
                  params={"select": "id", "store_id": "eq.5"})
    n = int(r.headers.get("content-range", "0-0/0").split("/")[-1])
    if n > 0:
        sys.exit(f"store_id=5 の行が既に {n} 件あります。二重投入防止のため中止します。")
    print("冪等確認OK: store_id=5 の既存行なし。")


def build() -> pd.DataFrame:
    set_master(build_master(os.path.join(os.path.dirname(__file__),
                                          "poc", "item_category_master.sql")))
    oi = pd.read_csv(os.path.join(SRC, "order_items.csv"), dtype=str)
    vs = pd.read_csv(os.path.join(SRC, "visits.csv"), dtype=str)
    oi["quantity"] = pd.to_numeric(oi["quantity"], errors="coerce").fillna(0)
    oi["unit_price"] = pd.to_numeric(oi["unit_price"], errors="coerce").fillna(0)
    oi["order_seq"] = pd.to_numeric(oi["order_seq"], errors="coerce")
    oi["line_index"] = pd.to_numeric(oi["line_index"], errors="coerce")
    oi["ordered_at"] = pd.to_datetime(oi["ordered_at"], errors="coerce")
    vs["party_size"] = pd.to_numeric(vs["party_size"], errors="coerce").fillna(0).astype(int)
    vs["visit_start"] = pd.to_datetime(vs["visit_start"], errors="coerce")

    df = oi.merge(
        vs[["visit_id", "store_id", "receipt_no", "party_size", "visit_start",
            "customer_layer", "customer_layer2"]],
        on=["visit_id", "store_id"], how="inner",
    )
    n0 = len(df)
    df = df[df["line_type"] == "M"]
    df = df[(df["ordered_at"] >= PERIOD_START) & (df["ordered_at"] < PERIOD_END)]
    hour = df["ordered_at"].dt.hour
    dow = df["ordered_at"].dt.dayofweek
    close = dow.map(lambda d: BT.CLOSE_SUNDAY if d == 6 else BT.CLOSE_DEFAULT)
    df = df[(hour >= BT.OPEN_HOUR) & (hour < close)]
    df = df[~df["item_name"].isin(BT._exclusion_names())]
    df = df[~df["item_name"].map(lambda x: any(k in str(x) for k in BT._COURSE_KW))]
    df = df.copy()
    df["category"] = df["item_name"].map(classify)
    df = df[df["category"] != "除外"]
    df["fd"] = df["category"].map(lambda c: "ドリンク" if c == "ドリンク" else "フード")
    df = df[~df["item_name"].map(lambda x: any(k in str(x) for k in BT._EXCLUDE_ITEM_KW))]
    print(f"加工: {n0}行 → {len(df)}行 / 来店{df.visit_id.nunique()} / オーダー{df.order_id.nunique()}")
    return df.reset_index(drop=True)


def _jst(ts: pd.Timestamp):
    # JSTナイーブ値に +09:00 を付ける（Postgresが正しいUTCへ正規化）
    if pd.isna(ts):
        return None
    return ts.strftime("%Y-%m-%dT%H:%M:%S") + "+09:00"


def to_records(df: pd.DataFrame) -> list[dict]:
    recs = []
    for _, r in df.iterrows():
        recs.append({
            "visit_id": r["visit_id"], "store_id": r["store_id"],
            "receipt_no": r.get("receipt_no"),
            "party_size": int(r["party_size"]) if pd.notna(r["party_size"]) else None,
            "visit_start": _jst(r["visit_start"]),
            "order_id": r["order_id"],
            "order_seq": int(r["order_seq"]) if pd.notna(r["order_seq"]) else None,
            "line_index": int(r["line_index"]) if pd.notna(r["line_index"]) else None,
            "ordered_at": _jst(r["ordered_at"]),
            "item_name": r["item_name"], "category": r["category"], "fd": r["fd"],
            "quantity": float(r["quantity"]), "unit_price": float(r["unit_price"]),
            "customer_layer": r.get("customer_layer"),
            "customer_layer2": r.get("customer_layer2"),
        })
    return recs


def insert(recs: list[dict]) -> None:
    hw = {"apikey": SVC, "Authorization": f"Bearer {SVC}",
          "Content-Type": "application/json", "Prefer": "return=minimal"}
    B = 500
    with httpx.Client(timeout=120) as c:
        for i in range(0, len(recs), B):
            chunk = recs[i:i + B]
            r = c.post(f"{URL}/rest/v1/{TABLE}", headers=hw, json=chunk)
            r.raise_for_status()
            print(f"  INSERT {i + len(chunk)}/{len(recs)}")


def verify() -> None:
    r = httpx.get(f"{URL}/rest/v1/{TABLE}",
                  headers={"apikey": KEY, "Authorization": f"Bearer {KEY}",
                           "Prefer": "count=exact", "Range": "0-0"},
                  params={"select": "id", "store_id": "eq.5"})
    n = int(r.headers.get("content-range", "0-0/0").split("/")[-1])
    print(f"検証: store_id=5 の行数 = {n}")
    r2 = httpx.get(f"{URL}/rest/v1/{TABLE}",
                   headers={"apikey": KEY, "Authorization": f"Bearer {KEY}"},
                   params={"select": "customer_layer,customer_layer2,category",
                           "store_id": "eq.5", "limit": 3})
    print("  サンプル:", r2.json())


def main() -> None:
    _check_alter()
    _idempotency()
    df = build()
    recs = to_records(df)
    print(f"投入件数: {len(recs)}")
    insert(recs)
    verify()
    print("完了。")


if __name__ == "__main__":
    main()
