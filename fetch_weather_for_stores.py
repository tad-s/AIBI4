"""
fetch_weather_for_stores.py
各店舗の位置情報をもとに Open-Meteo から日別天気を取得し、
Supabase の weather_locations / daily_weather テーブルに登録する。

事前準備:
  1. Supabase SQL Editor で etc/create_daily_weather.sql を実行
  2. python geocode_stores.py が完了していること（stores_master.csv に lat/lon あり）
  3. python fetch_weather_for_stores.py
"""

import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import calendar
import time
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))
from supabase_loader import get_client

DATA_DIR = Path(__file__).parent / "data"

# ── Open-Meteo グリッド精度 ─────────────────────────────────────────────
# 0.01° ≈ 1.1km: 同市内の店舗は同一地点の天気を共有する
GRID_PRECISION = 2

# ── WMO 天気コード → 日本語ラベル ───────────────────────────────────────
WEATHER_LABELS = {
    0:  "快晴",
    1:  "晴れ",        2:  "薄曇り",       3:  "曇り",
    45: "霧",           48: "霧氷",
    51: "霧雨(弱)",     53: "霧雨",         55: "霧雨(強)",
    61: "雨(弱)",       63: "雨",           65: "雨(強)",
    71: "雪(弱)",       73: "雪",           75: "雪(強)",
    77: "あられ",
    80: "にわか雨(弱)", 81: "にわか雨",     82: "にわか雨(強)",
    85: "にわか雪(弱)", 86: "にわか雪(強)",
    95: "雷雨",         96: "雷雨(ひょう)", 99: "激しい雷雨",
}

# ── 取得日付範囲のデフォルト ────────────────────────────────────────────
DEFAULT_START = "2024-09-01"
DEFAULT_END   = "2025-10-31"


# ────────────────────────────────────────────────────────────────────────
# ユーティリティ
# ────────────────────────────────────────────────────────────────────────

def get_date_range() -> tuple[str, str]:
    """data/ 内の sales_YYYYMM.csv のファイル名から日付範囲を推定する。"""
    csvs = sorted(DATA_DIR.glob("sales_2*.csv"))
    months = []
    for f in csvs:
        stem = f.stem  # e.g. "sales_202409"
        ym = stem.replace("sales_", "")
        if len(ym) == 6 and ym.isdigit():
            months.append(ym)
    if not months:
        print(f"    CSV が見つからないため既定範囲を使用: {DEFAULT_START} 〜 {DEFAULT_END}")
        return DEFAULT_START, DEFAULT_END
    start_ym = min(months)
    end_ym   = max(months)
    start_str = f"{start_ym[:4]}-{start_ym[4:6]}-01"
    y, m = int(end_ym[:4]), int(end_ym[4:6])
    last_day = calendar.monthrange(y, m)[1]
    end_str = f"{y}-{m:02d}-{last_day}"
    return start_str, end_str


def round_grid(val: float) -> float:
    return round(val, GRID_PRECISION)


# ────────────────────────────────────────────────────────────────────────
# Open-Meteo 取得
# ────────────────────────────────────────────────────────────────────────

def fetch_open_meteo(lat: float, lon: float, start_date: str, end_date: str) -> pd.DataFrame | None:
    """
    Open-Meteo Archive API から日別天気を取得する。
    Returns: DataFrame with columns [date, temperature_2m_max, ..., weather_label]
             or None on error
    """
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude":   lat,
        "longitude":  lon,
        "start_date": start_date,
        "end_date":   end_date,
        "daily": ",".join([
            "temperature_2m_max",
            "temperature_2m_min",
            "temperature_2m_mean",
            "precipitation_sum",
            "weathercode",
        ]),
        "timezone": "Asia/Tokyo",
    }
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        daily = data.get("daily", {})
        times = daily.get("time", [])
        if not times:
            print("    ⚠️  Open-Meteo: データなし")
            return None

        df = pd.DataFrame({
            "date":                times,  # "YYYY-MM-DD" 文字列
            "temperature_2m_max":  daily.get("temperature_2m_max"),
            "temperature_2m_min":  daily.get("temperature_2m_min"),
            "temperature_2m_mean": daily.get("temperature_2m_mean"),
            "precipitation_sum":   daily.get("precipitation_sum"),
            "weathercode":         daily.get("weathercode"),
        })
        df["weather_label"] = (
            df["weathercode"]
            .map(WEATHER_LABELS)
            .fillna("")
        )
        return df

    except requests.exceptions.HTTPError as e:
        print(f"    Open-Meteo HTTP エラー: {e}")
        return None
    except Exception as e:
        print(f"    Open-Meteo エラー: {e}")
        return None


# ────────────────────────────────────────────────────────────────────────
# Supabase 操作
# ────────────────────────────────────────────────────────────────────────

def upsert_location(sb, lat_grid: float, lon_grid: float, label: str) -> int | None:
    """weather_locations に UPSERT し、location_id を返す。"""
    try:
        res = sb.table("weather_locations").upsert(
            {"lat_grid": lat_grid, "lon_grid": lon_grid, "label": label},
            on_conflict="lat_grid,lon_grid",
        ).execute()
        # upsert 結果から location_id を取得
        if res.data:
            return res.data[0]["location_id"]
        # フォールバック: SELECT
        res2 = (
            sb.table("weather_locations")
            .select("location_id")
            .eq("lat_grid", lat_grid)
            .eq("lon_grid", lon_grid)
            .single()
            .execute()
        )
        return res2.data["location_id"]
    except Exception as e:
        print(f"    weather_locations upsert エラー: {e}")
        return None


def update_store_location_id(sb, store_id: int, location_id: int) -> bool:
    """stores.location_id を更新する。"""
    try:
        sb.table("stores").update({"location_id": location_id}).eq("store_id", store_id).execute()
        return True
    except Exception as e:
        print(f"    stores[{store_id}] location_id 更新エラー: {e}")
        return False


def upsert_weather_rows(sb, location_id: int, df: pd.DataFrame) -> int:
    """daily_weather に UPSERT する（バッチ 200 行）。"""
    records = []
    for _, row in df.iterrows():
        def _val(v):
            return None if pd.isna(v) else v

        wc = _val(row["weathercode"])
        records.append({
            "location_id":         location_id,
            "date":                str(row["date"]),
            "temperature_2m_max":  _val(row["temperature_2m_max"]),
            "temperature_2m_min":  _val(row["temperature_2m_min"]),
            "temperature_2m_mean": _val(row["temperature_2m_mean"]),
            "precipitation_sum":   _val(row["precipitation_sum"]),
            "weathercode":         int(wc) if wc is not None else None,
            "weather_label":       row["weather_label"] or None,
        })

    BATCH = 200
    inserted = 0
    for i in range(0, len(records), BATCH):
        batch = records[i : i + BATCH]
        try:
            sb.table("daily_weather").upsert(
                batch,
                on_conflict="location_id,date",
            ).execute()
            inserted += len(batch)
        except Exception as e:
            print(f"    daily_weather upsert エラー (batch {i}~{i+BATCH}): {e}")
    return inserted


# ────────────────────────────────────────────────────────────────────────
# メイン
# ────────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("店舗別 天気データ取得・登録スクリプト")
    print("=" * 60)

    # Supabase 接続
    print("\n[1] Supabase に接続中...")
    try:
        sb = get_client()
        print("    ✅ 接続成功")
    except Exception as e:
        print(f"    ❌ 接続失敗: {e}")
        sys.exit(1)

    # 店舗マスタ読み込み（緯度・経度があるもののみ）
    print("\n[2] 店舗マスタ読み込み...")
    master_path = DATA_DIR / "stores_master.csv"
    if not master_path.exists():
        print(f"    ❌ {master_path} が見つかりません。先に geocode_stores.py を実行してください。")
        sys.exit(1)

    df_stores = pd.read_csv(master_path, encoding="utf-8-sig")
    df_valid  = df_stores.dropna(subset=["latitude", "longitude"]).copy()
    skipped   = len(df_stores) - len(df_valid)
    print(f"    対象: {len(df_valid)} 店舗（緯度経度なし {skipped} 件を除外）")

    # グリッド座標でグループ化（0.01° ≈ 1km）
    df_valid["lat_grid"] = df_valid["latitude"].apply(round_grid)
    df_valid["lon_grid"] = df_valid["longitude"].apply(round_grid)

    location_groups  = df_valid.groupby(["lat_grid", "lon_grid"])
    unique_locations = list(location_groups.groups.keys())
    print(f"    ユニーク地点数: {len(unique_locations)} 地点（グリッド精度: 0.01°≈1km）")

    # 日付範囲を推定
    start_date, end_date = get_date_range()
    print(f"\n[3] 取得日付範囲: {start_date} 〜 {end_date}")

    # ────────────────────────────────────────────
    # Step 4: weather_locations 登録 & stores.location_id 更新
    # ────────────────────────────────────────────
    print("\n[4] weather_locations テーブルに地点を登録...")
    loc_id_map: dict[tuple[float, float], int] = {}

    for lat_grid, lon_grid in unique_locations:
        group  = location_groups.get_group((lat_grid, lon_grid))
        names  = group["store_name"].tolist()
        label  = ", ".join(names[:3]) + ("..." if len(names) > 3 else "")
        print(f"  ({lat_grid:.2f}, {lon_grid:.2f})  {label}")

        loc_id = upsert_location(sb, lat_grid, lon_grid, label)
        if loc_id is None:
            print(f"    ❌ location_id 取得失敗。スキップ。")
            continue

        loc_id_map[(lat_grid, lon_grid)] = loc_id
        print(f"    → location_id = {loc_id}")

        for _, store_row in group.iterrows():
            sid   = int(store_row["store_id"])
            sname = store_row["store_name"]
            if update_store_location_id(sb, sid, loc_id):
                print(f"    stores[{sid}] {sname} → location_id={loc_id}")

    # ────────────────────────────────────────────
    # Step 5: Open-Meteo から天気取得 & daily_weather 登録
    # ────────────────────────────────────────────
    print("\n[5] Open-Meteo から天気データを取得・登録...")
    total_inserted = 0
    failed_locs    = []
    weather_cache: dict[tuple[float, float], pd.DataFrame] = {}

    items = list(loc_id_map.items())
    for idx, ((lat_grid, lon_grid), loc_id) in enumerate(items):
        group = location_groups.get_group((lat_grid, lon_grid))
        names = group["store_name"].tolist()
        print(f"\n  [{idx+1}/{len(items)}] ({lat_grid:.2f}, {lon_grid:.2f})  {', '.join(names[:2])}")
        print(f"           location_id={loc_id}")

        df_w = fetch_open_meteo(lat_grid, lon_grid, start_date, end_date)
        if df_w is None or df_w.empty:
            print(f"    ❌ 天気データ取得失敗")
            failed_locs.append((lat_grid, lon_grid))
            continue

        print(f"    取得: {len(df_w)} 日分")
        n = upsert_weather_rows(sb, loc_id, df_w)
        print(f"    ✅ {n} 行 登録完了")
        total_inserted += n

        weather_cache[(lat_grid, lon_grid)] = df_w

        # Open-Meteo レートリミット対策（無料 API: ~10,000 req/day）
        time.sleep(0.5)

    # ────────────────────────────────────────────
    # Step 6: ローカルバックアップ CSV 保存
    # ────────────────────────────────────────────
    print("\n[6] ローカルバックアップ CSV を保存...")
    all_dfs = []
    for (lat_grid, lon_grid), df_w in weather_cache.items():
        df_copy = df_w.copy()
        df_copy["location_id"] = loc_id_map[(lat_grid, lon_grid)]
        df_copy["lat_grid"]    = lat_grid
        df_copy["lon_grid"]    = lon_grid
        all_dfs.append(df_copy)

    if all_dfs:
        df_all = pd.concat(all_dfs, ignore_index=True)
        out    = DATA_DIR / "daily_weather.csv"
        df_all.to_csv(out, index=False, encoding="utf-8-sig")
        print(f"    ✅ {out.name} ({len(df_all):,} 行, {out.stat().st_size/1024:,.1f} KB)")
    else:
        print("    ⚠️  保存するデータがありません")

    # ────────────────────────────────────────────
    # サマリー
    # ────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("完了サマリー")
    print(f"{'='*60}")
    print(f"  登録地点数     : {len(loc_id_map)}")
    print(f"  daily_weather  : {total_inserted:,} 行 登録")
    if failed_locs:
        print(f"  失敗地点 ({len(failed_locs)} 件):")
        for lat, lon in failed_locs:
            print(f"    ({lat:.2f}, {lon:.2f})")
    print()
    print("次のステップ:")
    print("  ・Supabase でデータ確認:")
    print("    SELECT * FROM daily_weather LIMIT 10;")
    print("  ・売上データ取得時に天気列が自動的に付与されます")
    print("    （get_izakaya_sales の LEFT JOIN で結合済み）")


if __name__ == "__main__":
    main()
