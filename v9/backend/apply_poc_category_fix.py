"""PoC専用テーブル poc_ikebukuro_items のカテゴリ修正を一括適用する。

classify._match 正規化バグ修正(commit 5124dd8)を経路B(保存済みカテゴリ)へ反映する。
現行テーブルを再分類し、差分のある商品だけを PATCH する（原本は不変）。
service key が必要（.env の SUPABASE_SERVICE_KEY）。

実行: cd v9/backend && ../../v8/backend/.venv/Scripts/python.exe apply_poc_category_fix.py
"""
import os
import sys

import httpx
import pandas as pd
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

import poc.classify as C
from poc.overrides import build_master

URL = os.getenv("SUPABASE_URL")
SVC = os.getenv("SUPABASE_SERVICE_KEY")
TABLE = "poc_ikebukuro_items"
PAGE = 1000

if not (URL and SVC):
    sys.exit("SUPABASE_URL / SUPABASE_SERVICE_KEY が未設定です（.env を確認）。")

# テーブル構築と同じマスタで分類器を初期化（同梱SQL優先）
C.set_master(build_master(os.path.join(os.path.dirname(__file__), "poc", "item_category_master.sql")))

hdr = {"apikey": SVC, "Authorization": f"Bearer {SVC}"}


def fetch_all() -> pd.DataFrame:
    rows, off = [], 0
    with httpx.Client(timeout=60) as c:
        while True:
            r = c.get(f"{URL}/rest/v1/{TABLE}",
                      headers={**hdr, "Range": f"{off}-{off + PAGE - 1}"},
                      params={"select": "item_name,category"})
            r.raise_for_status()
            b = r.json()
            rows += b
            if len(b) < PAGE:
                break
            off += PAGE
    return pd.DataFrame(rows)


def main() -> None:
    df = fetch_all()
    g = df.groupby("item_name").agg(cur=("category", "first"),
                                    rows=("item_name", "size")).reset_index()
    g["new"] = g["item_name"].map(C.classify)
    chg = g[(g["cur"] != g["new"]) & (g["new"] != "除外")].sort_values("rows", ascending=False)

    if chg.empty:
        print("差分なし。テーブルは最新の分類と一致しています。")
        return

    print(f"変更対象: {len(chg)}商品 / {int(chg['rows'].sum())}行")
    for _, r in chg.iterrows():
        print(f"  {r['item_name']}: {r['cur']} -> {r['new']} ({r['rows']}行)")

    with httpx.Client(timeout=60) as c:
        hw = {**hdr, "Content-Type": "application/json", "Prefer": "return=minimal"}
        for _, r in chg.iterrows():
            item, new = r["item_name"], r["new"]
            fd = "ドリンク" if new == "ドリンク" else "フード"
            pr = c.patch(f"{URL}/rest/v1/{TABLE}", headers=hw,
                         params={"item_name": f"eq.{item}"},
                         json={"category": new, "fd": fd})
            pr.raise_for_status()
            print(f"  PATCH OK: {item} -> {new}/{fd}")

    # 検証
    df2 = fetch_all()
    g2 = df2.groupby("item_name")["category"].first()
    bad = [(r["item_name"], g2.get(r["item_name"]), r["new"])
           for _, r in chg.iterrows() if g2.get(r["item_name"]) != r["new"]]
    if bad:
        print("検証NG:", bad)
        sys.exit(1)
    print("検証OK: 全変更が反映されました。")


if __name__ == "__main__":
    main()
