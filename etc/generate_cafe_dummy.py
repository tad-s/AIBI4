#!/usr/bin/env python3
"""
generate_cafe_dummy.py
カフェレストラン「Cafe Bloom」のダミーデータを Supabase に投入するスクリプト。

実行前提:
  1. etc/cafe_setup.sql を Supabase SQL Editor で実行済みであること
  2. C:\\Users\\tarchi\\AIBI4\\.env に SUPABASE_URL / SUPABASE_KEY が設定済みであること

実行方法（AIBI4 ルートから）:
  python etc/generate_cafe_dummy.py

投入データ:
  - weather_locations: 5地点追加（恵比寿・川崎・藤沢・千葉・柏）
  - daily_weather    : 新規5地点の 2024-09-01〜2025-10-31 実測天気（Open-Meteo）
  - cafe_stores      : 10店舗（東京5 / 神奈川3 / 千葉2）
  - cafe_visits      : 約5,000〜8,000件（4ヶ月分）
  - cafe_orders      : visits と同数
  - cafe_order_items : 約15,000〜25,000件

再実行する場合は先に Supabase SQL Editor で以下を実行してください:
  TRUNCATE cafe_order_items, cafe_orders, cafe_visits, cafe_stores RESTART IDENTITY CASCADE;
"""
import os
import sys
import random
import time
from datetime import datetime, timedelta, date, timezone
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

try:
    from supabase import create_client
except ImportError:
    print("ERROR: supabase パッケージが見つかりません。pip install supabase を実行してください。")
    sys.exit(1)

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: .env に SUPABASE_URL / SUPABASE_KEY が設定されていません。")
    sys.exit(1)

client = create_client(SUPABASE_URL, SUPABASE_KEY)
random.seed(42)

JST   = timezone(timedelta(hours=9))
UTC   = timezone.utc
BATCH = 500

WEATHER_START = "2024-09-01"
WEATHER_END   = "2025-10-31"

MONTHS = [
    ("2024-09-01", "2024-09-30"),
    ("2024-10-01", "2024-10-31"),
    ("2025-09-01", "2025-09-30"),
    ("2025-10-01", "2025-10-31"),
]

# ──────────────────────────────────────────────────────────────
# マスタデータ定義
# ──────────────────────────────────────────────────────────────

# 既存 weather_locations を流用する店舗の (lat_grid, lon_grid):
#   渋谷(35.66,139.70)=5, 新宿(35.69,139.70)=12, 池袋(35.73,139.71)=17,
#   銀座(35.67,139.76)=8, 横浜(35.47,139.62)=4
# 新規追加する5地点:
NEW_WEATHER_LOCATIONS = [
    {"lat_grid": 35.65, "lon_grid": 139.71, "label": "恵比寿"},
    {"lat_grid": 35.53, "lon_grid": 139.70, "label": "川崎"},
    {"lat_grid": 35.34, "lon_grid": 139.49, "label": "藤沢"},
    {"lat_grid": 35.61, "lon_grid": 140.11, "label": "千葉"},
    {"lat_grid": 35.86, "lon_grid": 139.98, "label": "柏"},
]

# (store_name, shop_code, area, address, lat, lon, (lat_grid, lon_grid))
STORES_DEF = [
    ("Cafe Bloom 渋谷店",        "CB01", "東京",   "東京都渋谷区道玄坂1-12-1",            35.6580, 139.7014, (35.66, 139.70)),
    ("Cafe Bloom 新宿店",        "CB02", "東京",   "東京都新宿区新宿3-38-1",              35.6916, 139.6979, (35.69, 139.70)),
    ("Cafe Bloom 池袋東口店",    "CB03", "東京",   "東京都豊島区東池袋1-11-1",            35.7308, 139.7119, (35.73, 139.71)),
    ("Cafe Bloom 銀座店",        "CB04", "東京",   "東京都中央区銀座4-6-1",               35.6716, 139.7648, (35.67, 139.76)),
    ("Cafe Bloom 恵比寿店",      "CB05", "東京",   "東京都渋谷区恵比寿1-7-1",            35.6464, 139.7101, (35.65, 139.71)),
    ("Cafe Bloom みなとみらい店","CB06", "神奈川", "神奈川県横浜市西区みなとみらい2-2-1", 35.4553, 139.6311, (35.47, 139.62)),
    ("Cafe Bloom 川崎店",        "CB07", "神奈川", "神奈川県川崎市川崎区駅前本町26-1",   35.5309, 139.7025, (35.53, 139.70)),
    ("Cafe Bloom 藤沢店",        "CB08", "神奈川", "神奈川県藤沢市南藤沢21-1",            35.3394, 139.4928, (35.34, 139.49)),
    ("Cafe Bloom 千葉店",        "CB09", "千葉",   "千葉県千葉市中央区富士見2-3-1",       35.6078, 140.1063, (35.61, 140.11)),
    ("Cafe Bloom 柏店",          "CB10", "千葉",   "千葉県柏市柏1-3-30",                  35.8631, 139.9759, (35.86, 139.98)),
]

# (name, price, weight, [slots])  slots: morning/lunch/cafe/dinner
MENU = [
    # モーニング
    ("モーニングセット（トースト＆卵）",  980, 4, ["morning"]),
    ("フレンチトースト",                 1050, 3, ["morning", "cafe"]),
    # ランチ
    ("日替わりランチプレート",           1280, 5, ["lunch"]),
    ("パスタランチ（スープ・サラダ付）", 1380, 4, ["lunch"]),
    ("ガレット（ベーコン＆エッグ）",     1200, 3, ["lunch"]),
    ("アボカドチキンサンドセット",       1100, 3, ["lunch"]),
    ("サラダボウル（グリルチキン）",      980, 3, ["lunch", "cafe"]),
    # カフェタイム
    ("本日のケーキセット",               1100, 4, ["cafe"]),
    ("パンケーキ（メープルバター）",     1150, 3, ["morning", "cafe"]),
    ("スコーン（クロテッドクリーム付）",   680, 2, ["cafe"]),
    ("ワッフル（季節のフルーツ添え）",     920, 2, ["cafe"]),
    # ディナー
    ("前菜盛り合わせ",                   980, 2, ["dinner"]),
    ("本日のキッシュプレート",           1250, 2, ["dinner"]),
    ("マルゲリータピザ",                 1450, 3, ["dinner"]),
    ("トマトパスタ",                     1250, 3, ["dinner", "lunch"]),
    ("カルボナーラ",                     1350, 3, ["dinner"]),
    ("きのこリゾット",                   1280, 2, ["dinner"]),
    ("チーズプレート",                   1200, 2, ["dinner"]),
    # ドリンク（全時間帯）
    ("ドリップコーヒー",                   520, 8, ["morning", "lunch", "cafe", "dinner"]),
    ("カフェラテ",                         600, 7, ["morning", "lunch", "cafe", "dinner"]),
    ("カプチーノ",                         600, 4, ["morning", "lunch", "cafe", "dinner"]),
    ("アイスコーヒー",                     540, 6, ["morning", "lunch", "cafe", "dinner"]),
    ("抹茶ラテ",                           660, 5, ["morning", "lunch", "cafe", "dinner"]),
    ("チャイティーラテ",                   640, 4, ["morning", "lunch", "cafe", "dinner"]),
    ("フレッシュオレンジジュース",          720, 3, ["morning", "lunch", "cafe", "dinner"]),
    ("スムージー（フルーツ）",              780, 3, ["morning", "lunch", "cafe", "dinner"]),
    ("レモネード",                          560, 4, ["morning", "lunch", "cafe", "dinner"]),
    ("ハーブティー",                        580, 3, ["morning", "lunch", "cafe", "dinner"]),
    ("クラフトビール（生）",                720, 3, ["dinner", "lunch"]),
    ("白ワイン（グラス）",                  780, 2, ["dinner"]),
    ("赤ワイン（グラス）",                  780, 2, ["dinner"]),
    ("ソフトドリンク",                      430, 5, ["morning", "lunch", "cafe", "dinner"]),
]

CUSTOMER_LAYERS = ["ソロ客", "カップル", "グループ", "ファミリー", "ビジネスランチ"]
LAYER_WEIGHTS = {
    "morning": [35, 20, 10, 10, 25],
    "lunch":   [20, 20, 15, 10, 35],
    "cafe":    [20, 35, 20, 15, 10],
    "dinner":  [15, 35, 25, 15, 10],
}
LAYER_SIZE = {
    "ソロ客":         (1, 1),
    "カップル":       (2, 2),
    "グループ":       (3, 5),
    "ファミリー":     (2, 4),
    "ビジネスランチ": (2, 4),
}
SLOT_HOURS = {
    "morning": (8,  11),
    "lunch":   (11, 15),
    "cafe":    (14, 18),
    "dinner":  (17, 21),
}


# ──────────────────────────────────────────────────────────────
# ユーティリティ
# ──────────────────────────────────────────────────────────────

def _weathercode_label(code: Optional[int]) -> str:
    if code is None:
        return "不明"
    code = int(code)
    if code == 0:
        return "晴れ"
    if code in (1, 2, 3):
        return "曇り"
    if (51 <= code <= 67) or (80 <= code <= 82):
        return "雨"
    if (71 <= code <= 77) or code in (85, 86):
        return "雪"
    return "その他"


def fetch_weather(lat: float, lon: float) -> list[dict]:
    """Open-Meteo Archive API から天気データを取得。"""
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": lat, "longitude": lon,
        "start_date": WEATHER_START, "end_date": WEATHER_END,
        "daily": "temperature_2m_max,temperature_2m_min,temperature_2m_mean,precipitation_sum,weathercode",
        "timezone": "Asia/Tokyo",
    }
    for attempt in range(3):
        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            d = resp.json()["daily"]
            return [
                {
                    "date":                d["time"][i],
                    "temperature_2m_max":  d["temperature_2m_max"][i],
                    "temperature_2m_min":  d["temperature_2m_min"][i],
                    "temperature_2m_mean": d["temperature_2m_mean"][i],
                    "precipitation_sum":   d["precipitation_sum"][i],
                    "weathercode":         d["weathercode"][i],
                    "weather_label":       _weathercode_label(d["weathercode"][i]),
                }
                for i in range(len(d["time"]))
            ]
        except Exception as e:
            print(f"    警告 Open-Meteo ({attempt+1}/3): {e}")
            time.sleep(2 ** attempt)
    return []


def batch_insert(table: str, rows: list[dict], label: str = "") -> list[dict]:
    """行リストを BATCH サイズ単位でまとめて INSERT し、挿入済み行リストを返す。"""
    inserted = []
    for i in range(0, len(rows), BATCH):
        res = client.table(table).insert(rows[i:i + BATCH]).execute()
        inserted.extend(res.data or [])
    if label:
        print(f"    ✓ {table}: {len(rows):,} 件 {label}")
    return inserted


def to_utc(dt_jst: datetime) -> str:
    return dt_jst.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def pick_slot(d: date) -> str:
    is_wknd = d.weekday() >= 5
    if is_wknd:
        return random.choices(["morning", "lunch", "cafe", "dinner"], weights=[15, 25, 30, 30])[0]
    return random.choices(["morning", "lunch", "cafe", "dinner"], weights=[15, 35, 20, 30])[0]


def daily_visits(d: date) -> int:
    return random.randint(5, 12) if d.weekday() >= 5 else random.randint(3, 8)


def gen_items(slot: str, party_size: int) -> list[dict]:
    """1来店分の注文明細リストを生成（ドリンク人数分 + フード1〜3品）。"""
    slot_items = [(n, p, w) for n, p, w, slots in MENU if slot in slots]

    drink_kw = ("コーヒー", "ラテ", "ティー", "ジュース", "スムージー",
                "レモネード", "ビール", "ワイン", "ドリンク", "カプチーノ")
    drinks = [(n, p, w) for n, p, w in slot_items if any(k in n for k in drink_kw)]
    foods  = [(n, p, w) for n, p, w in slot_items if (n, p, w) not in drinks]

    items = []

    if drinks:
        dnames   = [x[0] for x in drinks]
        dprices  = {x[0]: x[1] for x in drinks}
        dweights = [x[2] for x in drinks]
        for dn in random.choices(dnames, weights=dweights, k=party_size):
            items.append({"item_name_raw": dn, "quantity": 1,
                          "unit_price": dprices[dn], "line_type": "M"})

    if foods:
        fnames   = [x[0] for x in foods]
        fprices  = {x[0]: x[1] for x in foods}
        fweights = [x[2] for x in foods]
        n_food = random.choices([1, 2, 3],
                                weights=[40, 45, 15] if party_size < 3 else [20, 45, 35])[0]
        for fn in random.choices(fnames, weights=fweights, k=n_food):
            items.append({"item_name_raw": fn, "quantity": 1,
                          "unit_price": fprices[fn], "line_type": "M"})

    return items


# ──────────────────────────────────────────────────────────────
# 投入ステップ
# ──────────────────────────────────────────────────────────────

def step1_weather_locations() -> dict:
    """新規5地点を weather_locations に upsert し、全地点の {(lat,lon): id} を返す。"""
    print("\n[Step 1] weather_locations 地点追加...")
    for loc in NEW_WEATHER_LOCATIONS:
        client.table("weather_locations").upsert(loc, on_conflict="lat_grid,lon_grid").execute()

    res = client.table("weather_locations").select("location_id,lat_grid,lon_grid").execute()
    grid_to_id = {}
    for row in (res.data or []):
        key = (round(float(row["lat_grid"]), 2), round(float(row["lon_grid"]), 2))
        grid_to_id[key] = row["location_id"]
    print(f"  ✓ 計 {len(grid_to_id)} 地点を確認")
    return grid_to_id


def step2_weather_data(grid_to_id: dict) -> None:
    """新規5地点の天気データを Open-Meteo から取得して daily_weather に投入。"""
    print("\n[Step 2] 天気データ取得・投入（新規5地点）...")
    for loc in NEW_WEATHER_LOCATIONS:
        key    = (loc["lat_grid"], loc["lon_grid"])
        loc_id = grid_to_id.get(key)
        if not loc_id:
            print(f"  ! {loc['label']}: location_id 取得失敗、スキップ")
            continue

        existing = client.table("daily_weather").select("date").eq("location_id", loc_id).limit(1).execute()
        if existing.data:
            print(f"  ↳ {loc['label']}: 既存データあり、スキップ")
            continue

        print(f"  → {loc['label']} ({loc['lat_grid']}, {loc['lon_grid']}) 取得中...")
        rows = fetch_weather(loc["lat_grid"], loc["lon_grid"])
        if not rows:
            print(f"    ! 取得失敗")
            continue
        weather_rows = [{"location_id": loc_id, **r} for r in rows]
        batch_insert("daily_weather", weather_rows, f"({loc['label']})")
        time.sleep(1)


def step3_stores(grid_to_id: dict) -> list[dict]:
    """cafe_stores に10店舗を投入して返す。既存データがあればスキップ。"""
    print("\n[Step 3] カフェ店舗データ投入...")
    existing = client.table("cafe_stores").select("store_id,store_name").execute()
    if existing.data:
        print(f"  ↳ 既に {len(existing.data)} 件あり、スキップ")
        return existing.data

    store_rows = []
    for name, code, area, addr, lat, lon, grid in STORES_DEF:
        store_rows.append({
            "store_name":      name,
            "shop_code":       code,
            "area_layer_name": area,
            "address":         addr,
            "latitude":        lat,
            "longitude":       lon,
            "location_id":     grid_to_id.get(grid),
        })

    inserted = batch_insert("cafe_stores", store_rows, "投入完了")
    return inserted


def step4_visits_orders_items(stores: list[dict]) -> None:
    """各月・各店舗のダミー来店・注文・明細データを生成して投入。"""
    print("\n[Step 4] 来店・注文・明細データ生成・投入...")

    existing = client.table("cafe_visits").select("visit_id").limit(1).execute()
    if existing.data:
        print("  ↳ cafe_visits に既にデータあり、スキップ")
        return

    store_ids = {s["store_name"]: s["store_id"] for s in stores}
    total_v, total_i = 0, 0

    for month_start, month_end in MONTHS:
        print(f"  → {month_start[:7]} 処理中...")
        start_d = date.fromisoformat(month_start)
        end_d   = date.fromisoformat(month_end)

        visit_rows    = []
        pending       = []   # {visit_idx, order_time, items}
        rcpt_counter  = 0

        cur = start_d
        while cur <= end_d:
            for sname, sid in sorted(store_ids.items()):
                for _ in range(daily_visits(cur)):
                    slot  = pick_slot(cur)
                    layer = random.choices(CUSTOMER_LAYERS, weights=LAYER_WEIGHTS[slot])[0]
                    pmin, pmax = LAYER_SIZE[layer]
                    psize = random.randint(pmin, pmax)

                    h_s, h_e = SLOT_HOURS[slot]
                    h = random.randint(h_s, h_e - 1)
                    m = random.randint(0, 59)
                    visit_dt = datetime(cur.year, cur.month, cur.day, h, m, tzinfo=JST)
                    leave_dt = visit_dt + timedelta(minutes=random.randint(25, 100))
                    order_dt = visit_dt + timedelta(minutes=random.randint(3, 10))

                    rcpt_counter += 1
                    receipt_no = f"CB{month_start[:4]}{month_start[5:7]}{sid:02d}{rcpt_counter:05d}"

                    visit_rows.append({
                        "store_id":       sid,
                        "receipt_no":     receipt_no,
                        "visit_time":     to_utc(visit_dt),
                        "leave_time":     to_utc(leave_dt),
                        "party_size":     psize,
                        "customer_layer": layer,
                    })
                    pending.append({
                        "visit_idx":  len(visit_rows) - 1,
                        "order_time": to_utc(order_dt),
                        "items":      gen_items(slot, psize),
                    })
            cur += timedelta(days=1)

        # visits 投入
        print(f"    visits {len(visit_rows):,} 件...")
        inserted_v = batch_insert("cafe_visits", visit_rows)

        # orders 投入
        order_rows = [
            {"visit_id": inserted_v[pv["visit_idx"]]["visit_id"], "order_time": pv["order_time"]}
            for pv in pending
        ]
        print(f"    orders {len(order_rows):,} 件...")
        inserted_o = batch_insert("cafe_orders", order_rows)

        # order_items 投入
        item_rows = []
        for oi, pv in enumerate(pending):
            oid = inserted_o[oi]["order_id"]
            for item in pv["items"]:
                item_rows.append({"order_id": oid, **item})
        print(f"    order_items {len(item_rows):,} 件...")
        batch_insert("cafe_order_items", item_rows)

        total_v += len(visit_rows)
        total_i += len(item_rows)
        print(f"    ✓ {month_start[:7]}: visits={len(visit_rows):,}, items={len(item_rows):,}")

    print(f"\n  合計: visits={total_v:,}, order_items={total_i:,}")


# ──────────────────────────────────────────────────────────────
# エントリポイント
# ──────────────────────────────────────────────────────────────

def main():
    print("=" * 55)
    print("  Cafe Bloom ダミーデータ投入スクリプト")
    print("=" * 55)

    grid_to_id = step1_weather_locations()
    step2_weather_data(grid_to_id)
    stores = step3_stores(grid_to_id)
    step4_visits_orders_items(stores)

    print("\n✅ 完了！")
    print("次のステップ:")
    print("  Streamlit アプリのサイドバー「☕ カフェ（Cafe Bloom）」を選択")
    print("  月を選択して「DB からデータを取得」を実行してください")


if __name__ == "__main__":
    main()
