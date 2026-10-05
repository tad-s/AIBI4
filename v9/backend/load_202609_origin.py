"""池袋東口 2026-09 の生データを【原本テーブル】visits/orders/order_items へ投入する。

経路A（通常ベース分析）で9月を扱えるようにする。PoC専用テーブルとは別の、本番中核テーブル
への書き込み。生データ全量（PoC除外なし）。store_id は原本の池袋東口=32 に再マップ。
時刻は JST(+09:00) で投入（原本の既存store32と同じ UTC 正規化）。customer_layer2 は
原本visitsに列が無いため投入しない。

冪等: 各テーブルで「store_id=32 かつ 2026-09」の既存行が無いことを確認してから投入。
実行: cd v9/backend && ../../v8/backend/.venv/Scripts/python.exe load_202609_origin.py
"""
import os
import sys

import httpx
import pandas as pd
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

URL = os.getenv("SUPABASE_URL")
SVC = os.getenv("SUPABASE_SERVICE_KEY")
SRC = os.path.join(os.path.dirname(__file__), "..", "..",
                   "data", "池袋東口店", "池袋東口店_追加データ202609")
STORE_ID = 32            # 原本の池袋東口（CSVの5から再マップ）
LOAD_TS = "2026-10-05T00:00:00+09:00"
BATCH = 500

if not (URL and SVC):
    sys.exit("SUPABASE_URL / SUPABASE_SERVICE_KEY が未設定です。")

HW = {"apikey": SVC, "Authorization": f"Bearer {SVC}",
      "Content-Type": "application/json", "Prefer": "return=minimal"}
HR = {"apikey": SVC, "Authorization": f"Bearer {SVC}"}


def jst(v):
    """JSTナイーブ文字列に +09:00 を付ける（空→None）。"""
    if v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() in ("", "nan", "NaT"):
        return None
    s = str(v).strip().replace(" ", "T")
    return s + "+09:00"


def val(v):
    if v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() in ("", "nan"):
        return None
    return str(v)


def inum(v):
    v = val(v)
    return int(float(v)) if v is not None else None


def fnum(v):
    v = val(v)
    return float(v) if v is not None else None


def insert(tbl: str, recs: list[dict]) -> None:
    with httpx.Client(timeout=120) as c:
        for i in range(0, len(recs), BATCH):
            chunk = recs[i:i + BATCH]
            r = c.post(f"{URL}/rest/v1/{tbl}", headers=HW, json=chunk)
            if r.status_code >= 300:
                sys.exit(f"[{tbl}] INSERT失敗 HTTP{r.status_code}: {r.text[:300]}")
            print(f"  [{tbl}] INSERT {i + len(chunk)}/{len(recs)}")


def build_visits() -> list[dict]:
    vs = pd.read_csv(os.path.join(SRC, "visits.csv"), dtype=str)
    recs = []
    for _, r in vs.iterrows():
        recs.append({
            "visit_id": r["visit_id"], "store_id": STORE_ID,
            "customer_id": val(r.get("customer_id")), "receipt_no": val(r.get("receipt_no")),
            "table_number": val(r.get("table_number")), "party_size": inum(r.get("party_size")),
            "customer_layer": val(r.get("customer_layer")),
            "visit_time": jst(r.get("visit_time")), "leave_time": jst(r.get("leave_time")),
            "visit_start": jst(r.get("visit_start")), "visit_end": jst(r.get("visit_end")),
            "generation": inum(r.get("generation")),
            "total_amount": fnum(r.get("total_amount")),
            "payment_method": val(r.get("payment_method")),
            "settlement_info_raw": val(r.get("settlement_info_raw")),
            "is_delivery": (str(r.get("is_delivery")).lower() == "true") if val(r.get("is_delivery")) is not None else None,
            "service_mode": val(r.get("service_mode")),
            "created_at": LOAD_TS,
            # customer_layer2 は原本visitsに列が無いため投入しない
        })
    return recs


def build_orders() -> list[dict]:
    od = pd.read_csv(os.path.join(SRC, "orders.csv"), dtype=str)
    return [{
        "order_id": r["order_id"], "visit_id": r["visit_id"],
        "order_seq": inum(r.get("order_seq")), "order_time": jst(r.get("order_time")),
        "created_at": LOAD_TS,
    } for _, r in od.iterrows()]


def build_items() -> list[dict]:
    oi = pd.read_csv(os.path.join(SRC, "order_items.csv"), dtype=str)
    recs = []
    for _, r in oi.iterrows():
        recs.append({
            "order_item_id": r["order_item_id"], "order_id": r["order_id"],
            "visit_id": r["visit_id"], "store_id": STORE_ID,
            "item_id": val(r.get("item_id")),
            "order_seq": inum(r.get("order_seq")), "line_index": inum(r.get("line_index")),
            "ordered_at": jst(r.get("ordered_at")),
            "menu_no": val(r.get("menu_no")), "grand_menu_no": val(r.get("grand_menu_no")),
            "item_name": val(r.get("item_name")), "line_type": val(r.get("line_type")),
            "quantity": inum(r.get("quantity")), "unit_price": fnum(r.get("unit_price")),
            "subtotal": fnum(r.get("subtotal")),
            "set_menu_no": val(r.get("set_menu_no")), "set_menu_name": val(r.get("set_menu_name")),
            "gm_seq_idx": val(r.get("gm_seq_idx")),
            "created_at": LOAD_TS,
        })
    return recs


def guard(tbl: str) -> None:
    col = "visit_start" if tbl == "visits" else ("order_time" if tbl == "orders" else "ordered_at")
    p = {"select": col, col: "gte.2026-09-01"}
    if tbl != "orders":
        p["store_id"] = f"eq.{STORE_ID}"
    r = httpx.get(f"{URL}/rest/v1/{tbl}", headers={**HR, "Prefer": "count=exact", "Range": "0-0"},
                  params=p, timeout=30)
    n = int(r.headers.get("content-range", "0-0/0").split("/")[-1])
    if n > 0:
        sys.exit(f"[{tbl}] 既に 2026-09 の行が {n} 件あります（store32）。二重投入防止のため中止。")


def main() -> None:
    builders = [("visits", build_visits), ("orders", build_orders), ("order_items", build_items)]
    # 冪等チェック（全テーブル）
    for tbl, _ in builders:
        guard(tbl)
    print("冪等確認OK: 3テーブルとも 2026-09(store32) の既存なし。\n")
    # 投入（visits→orders→order_items）
    for tbl, fn in builders:
        recs = fn()
        print(f"[{tbl}] 投入件数 {len(recs)}")
        insert(tbl, recs)
    # 検証
    print("\n=== 検証 ===")
    for tbl in ("visits", "orders", "order_items"):
        col = "visit_start" if tbl == "visits" else ("order_time" if tbl == "orders" else "ordered_at")
        p = {"select": col, col: "gte.2026-09-01"}
        if tbl != "orders":
            p["store_id"] = f"eq.{STORE_ID}"
        r = httpx.get(f"{URL}/rest/v1/{tbl}", headers={**HR, "Prefer": "count=exact", "Range": "0-0"}, params=p, timeout=30)
        print(f"  {tbl} 2026-09: {r.headers.get('content-range')}")
    # 月一覧に9月が出るか
    rm = httpx.post(f"{URL}/rest/v1/rpc/get_available_months",
                    headers={**HR, "Content-Type": "application/json"}, json={"p_dataset": "izakaya"}, timeout=30)
    months = [x.get("year_month") if isinstance(x, dict) else x for x in rm.json()]
    print("  月一覧に2026-09:", "2026-09" in months, "/ 末尾:", months[-3:])
    print("完了。")


if __name__ == "__main__":
    main()
