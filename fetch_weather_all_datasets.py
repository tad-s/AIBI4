"""
fetch_weather_all_datasets.py
全データセット（izakaya / cafe / bakery / salon）の天気データを
Open-Meteo Archive API から取得し、Supabase の daily_weather に登録する。

対象期間: 2024-01-01 〜 2025-12-31（全データセット共通）

事前準備:
  1. Supabase SQL Editor で etc/v8_weather_extend.sql を実行済みであること
  2. python fetch_weather_all_datasets.py
"""

import io
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))
from supabase_loader import get_client

# ── 取得日付範囲 ────────────────────────────────────────────────────────
FETCH_START = "2024-01-01"
FETCH_END   = "2025-12-31"

# ── WMO 天気コード → 日本語ラベル ───────────────────────────────────────
WEATHER_LABELS = {
    0:  "快晴",
    1:  "晴れ",        2:  "薄曇り",       3:  "曇り",
    45: "霧",          48: "霧氷",
    51: "霧雨(弱)",    53: "霧雨",         55: "霧雨(強)",
    61: "雨(弱)",      63: "雨",           65: "雨(強)",
    71: "雪(弱)",      73: "雪",           75: "雪(強)",
    77: "あられ",
    80: "にわか雨(弱)", 81: "にわか雨",     82: "にわか雨(強)",
    85: "にわか雪(弱)", 86: "にわか雪(強)",
    95: "雷雨",        96: "雷雨(ひょう)", 99: "激しい雷雨",
}

STORE_TABLES = [
    "stores",
    "cafe_stores",
    "bakery_stores",
    "salon_stores",
]


def fetch_open_meteo(lat: float, lon: float, start_date: str, end_date: str) -> pd.DataFrame | None:
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude":   lat,
        "longitude":  lon,
        "start_date": start_date,
        "end_date":   end_date,
        "daily": ",".join([
            "temperature_2m_max", "temperature_2m_min", "temperature_2m_mean",
            "precipitation_sum", "weathercode",
        ]),
        "timezone": "Asia/Tokyo",
    }
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        daily = resp.json().get("daily", {})
        times = daily.get("time", [])
        if not times:
            print("    ⚠️  データなし")
            return None
        df = pd.DataFrame({
            "date":                times,
            "temperature_2m_max":  daily.get("temperature_2m_max"),
            "temperature_2m_min":  daily.get("temperature_2m_min"),
            "temperature_2m_mean": daily.get("temperature_2m_mean"),
            "precipitation_sum":   daily.get("precipitation_sum"),
            "weathercode":         daily.get("weathercode"),
        })
        df["weather_label"] = df["weathercode"].map(WEATHER_LABELS).fillna("")
        return df
    except Exception as e:
        print(f"    ❌ Open-Meteo エラー: {e}")
        return None


def upsert_weather_rows(sb, location_id: int, df: pd.DataFrame) -> int:
    def _val(v):
        return None if pd.isna(v) else v

    records = [
        {
            "location_id":         location_id,
            "date":                str(row["date"]),
            "temperature_2m_max":  _val(row["temperature_2m_max"]),
            "temperature_2m_min":  _val(row["temperature_2m_min"]),
            "temperature_2m_mean": _val(row["temperature_2m_mean"]),
            "precipitation_sum":   _val(row["precipitation_sum"]),
            "weathercode":         int(_val(row["weathercode"])) if _val(row["weathercode"]) is not None else None,
            "weather_label":       row["weather_label"] or None,
        }
        for _, row in df.iterrows()
    ]
    inserted = 0
    BATCH = 200
    for i in range(0, len(records), BATCH):
        try:
            sb.table("daily_weather").upsert(
                records[i:i+BATCH],
                on_conflict="location_id,date",
            ).execute()
            inserted += len(records[i:i+BATCH])
        except Exception as e:
            print(f"    ❌ upsert エラー (batch {i}): {e}")
    return inserted


def main():
    print("=" * 60)
    print("全データセット 天気データ一括取得・登録")
    print(f"対象期間: {FETCH_START} 〜 {FETCH_END}")
    print("=" * 60)

    print("\n[1] Supabase 接続...")
    sb = get_client()
    print("    ✅ 接続成功")

    # 全ストアテーブルから使用中の location_id を収集
    print("\n[2] 使用中の location_id を収集...")
    used_loc_ids: set[int] = set()
    for table in STORE_TABLES:
        try:
            res = sb.table(table).select("location_id").not_.is_("location_id", "null").execute()
            ids = {row["location_id"] for row in (res.data or [])}
            print(f"    {table}: {sorted(ids)}")
            used_loc_ids |= ids
        except Exception as e:
            print(f"    {table}: スキップ ({e})")

    if not used_loc_ids:
        print("    ❌ location_id が 1 件も見つかりません")
        print("    → etc/v8_weather_extend.sql を Supabase SQL Editor で実行してください")
        sys.exit(1)

    # location_id → lat/lon の対応を取得
    print(f"\n[3] weather_locations テーブルから座標取得... ({len(used_loc_ids)} 地点)")
    res = sb.table("weather_locations").select("location_id,lat_grid,lon_grid,label").execute()
    loc_map = {
        row["location_id"]: (row["lat_grid"], row["lon_grid"], row.get("label", ""))
        for row in (res.data or [])
    }
    target_locs = {lid: loc_map[lid] for lid in used_loc_ids if lid in loc_map}
    print(f"    対象地点数: {len(target_locs)}")

    # Open-Meteo から取得して daily_weather に upsert
    print(f"\n[4] Open-Meteo から天気データを取得・登録...")
    total_inserted = 0
    failed = []

    for idx, (loc_id, (lat, lon, label)) in enumerate(sorted(target_locs.items())):
        print(f"\n  [{idx+1}/{len(target_locs)}] location_id={loc_id}  ({lat:.2f}, {lon:.2f})  {label}")
        df_w = fetch_open_meteo(lat, lon, FETCH_START, FETCH_END)
        if df_w is None or df_w.empty:
            failed.append(loc_id)
            continue
        print(f"    取得: {len(df_w)} 日分")
        n = upsert_weather_rows(sb, loc_id, df_w)
        print(f"    ✅ {n} 行 登録完了")
        total_inserted += n
        time.sleep(0.5)  # Open-Meteo レートリミット対策

    print(f"\n{'='*60}")
    print("完了サマリー")
    print(f"{'='*60}")
    print(f"  処理地点数:    {len(target_locs)}")
    print(f"  daily_weather: {total_inserted:,} 行 登録")
    if failed:
        print(f"  失敗 location_id: {failed}")
    print()


if __name__ == "__main__":
    main()
