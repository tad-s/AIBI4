"""Supabase summary_cache テーブル(id=1)を最新の visits から再集計する。

Streamlit app_v7_0._rebuild_summary_cache と同一ロジック（店舗×月／店舗×時間帯の
distinct 伝票数）。9月データ投入などを KPI ヒートマップへ反映するために実行する。
data/summary_cache.json も併せて更新する。

実行: ../../v8/backend/.venv/Scripts/python.exe rebuild_summary_cache.py
   （リポジトリ直下から: v8/backend/.venv/Scripts/python.exe rebuild_summary_cache.py）
"""
import json
import os
import sys
from datetime import datetime

import httpx
import pandas as pd
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

URL = os.getenv("SUPABASE_URL")
SVC = os.getenv("SUPABASE_SERVICE_KEY")
if not (URL and SVC):
    sys.exit("SUPABASE_URL / SUPABASE_SERVICE_KEY が未設定です。")
HR = {"apikey": SVC, "Authorization": f"Bearer {SVC}"}


def _page(tbl: str, cols: str) -> list[dict]:
    rows, off, P = [], 0, 1000
    with httpx.Client(timeout=120) as c:
        while True:
            r = c.get(f"{URL}/rest/v1/{tbl}", headers={**HR, "Range": f"{off}-{off + P - 1}"},
                      params={"select": cols})
            r.raise_for_status()
            b = r.json()
            rows += b
            if len(b) < P:
                break
            off += P
    return rows


def _band(h):
    if h < 17: return "〜17時(昼)"
    if h < 20: return "17〜20時(夕方)"
    if h < 23: return "20〜23時(夜)"
    return "23時〜(深夜)"


def main() -> None:
    stores = {s["store_id"]: s.get("store_name") for s in _page("stores", "store_id,store_name")}
    print(f"stores: {len(stores)} 件")
    vs = _page("visits", "visit_time,store_id,receipt_no")
    df = pd.DataFrame(vs)
    print(f"visits: {len(df)} 件 取得")
    df["store_name"] = df["store_id"].map(stores)
    jst = pd.to_datetime(df["visit_time"], format="ISO8601", errors="coerce", utc=True).dt.tz_convert("Asia/Tokyo")
    df["month"] = jst.dt.strftime("%Y-%m")
    df["time_band"] = jst.dt.hour.map(_band)
    df = df.dropna(subset=["month"])

    cur = pd.Timestamp.now(tz="Asia/Tokyo").strftime("%Y-%m")
    before = len(df)
    df = df[df["month"] <= cur]
    if before - len(df):
        print(f"未来月レコードを {before - len(df)} 件除外")

    store_month = (df.groupby(["store_name", "month"], sort=True)["receipt_no"]
                   .nunique().reset_index()
                   .rename(columns={"store_name": "店舗名", "receipt_no": "伝票数"}))
    store_timeband = (df.groupby(["store_name", "time_band"], sort=True)["receipt_no"]
                      .nunique().reset_index()
                      .rename(columns={"store_name": "店舗名", "receipt_no": "伝票数"}))

    cache = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_visits": int(len(df)),
        "store_month": store_month.to_dict(orient="records"),
        "store_timeband": store_timeband.to_dict(orient="records"),
    }
    months = sorted(store_month["month"].unique())
    print(f"集計: total_visits={cache['total_visits']} / 月範囲 {months[:2]}…{months[-3:]} / 2026-09含む={'2026-09' in months}")

    # Supabase summary_cache を upsert（id=1）
    hw = {**HR, "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates,return=minimal"}
    body = {"id": 1, "generated_at": cache["generated_at"], "total_visits": cache["total_visits"],
            "store_month": cache["store_month"], "store_timeband": cache["store_timeband"]}
    r = httpx.post(f"{URL}/rest/v1/summary_cache", headers=hw, json=body, timeout=60)
    if r.status_code >= 300:
        sys.exit(f"summary_cache upsert 失敗 HTTP{r.status_code}: {r.text[:300]}")
    print("summary_cache テーブル upsert 完了。")

    # ローカル json も更新
    out = {"generated_at": cache["generated_at"], "data_source": "supabase",
           "total_visits": cache["total_visits"], "store_month": cache["store_month"],
           "store_timeband": cache["store_timeband"]}
    path = os.path.join(os.path.dirname(__file__), "data", "summary_cache.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"data/summary_cache.json 更新完了。")
    print("完了。")


if __name__ == "__main__":
    main()
