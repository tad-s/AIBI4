"""外部接続なしで v10 を触るためのデモデータ生成（Supabase 不要）。

生成する DataFrame は `core.duck.Session.load()` がそのまま受け取れる
「商品明細(items)粒度」の最終スキーマに一致させる（transform を通さない）。
"""
from __future__ import annotations

import random

import pandas as pd

# デモの店舗・月（メタ情報エンドポイントと load で共有する）
DEMO_STORES = ["新宿店", "渋谷店", "神田店", "横浜店", "千葉店", "柏店"]
DEMO_MONTHS = ["2025-09", "2025-10"]

_CUSTOMER_LAYERS = ["会社員", "学生", "家族", "シニア", "少人数宴会"]
_WEATHER_LABELS = ["晴れ", "曇り", "雨"]
_MENU = {
    "ドリンク": [
        ("生ビール", 590), ("ハイボール", 490), ("レモンサワー", 520),
        ("ウーロン茶", 350), ("日本酒", 680),
    ],
    "揚げ物": [("唐揚げ", 680), ("ポテトフライ", 480), ("チキン南蛮", 780)],
    "串": [("焼き鳥盛合せ", 890), ("つくね", 260), ("ねぎま", 240)],
    "海鮮": [("刺身盛り", 1280), ("炙りしめ鯖", 780), ("たこぶつ", 620)],
    "軽いつまみ": [("枝豆", 390), ("冷奴", 360), ("漬物盛り", 420)],
    "食事": [("焼きおにぎり", 390), ("鶏雑炊", 690), ("ソース焼きそば", 780)],
}


def demo_store_options() -> list[dict]:
    """/api/stores のデモ版（store_id は一覧のインデックスで安定）。"""
    return [{"store_id": i, "store_name": name} for i, name in enumerate(DEMO_STORES)]


def demo_months() -> list[str]:
    return list(DEMO_MONTHS)


def _store_names_from_ids(store_ids: list[int] | None) -> list[str] | None:
    if not store_ids:
        return None
    return [DEMO_STORES[i] for i in store_ids if 0 <= i < len(DEMO_STORES)]


def build_demo_items_df(
    months: list[str] | None = None,
    store_ids: list[int] | None = None,
    seed: int = 12,
    orders: int = 640,
) -> pd.DataFrame:
    """デモの商品明細 DataFrame を生成し、月・店舗で絞り込んで返す。"""
    random.seed(seed)
    rows: list[dict] = []
    for receipt_no in range(orders):
        store_name = random.choice(DEMO_STORES)
        month = random.choice([9, 10])
        day = random.randint(1, 28)
        hour = random.choices(
            [11, 12, 17, 18, 19, 20, 21, 22], weights=[2, 3, 6, 10, 12, 10, 7, 3]
        )[0]
        visit_time = pd.Timestamp(2025, month, day, hour, random.choice([0, 15, 30, 45]))
        party_size = random.choices([1, 2, 3, 4, 5, 6], weights=[12, 36, 20, 18, 8, 6])[0]
        item_count = random.randint(max(1, party_size), max(3, party_size * 4))
        stay_minutes = random.randint(35, 150)
        visit_key = f"{visit_time.strftime('%Y%m%d%H%M%S')}_D{receipt_no:05d}"
        weather = random.choice(_WEATHER_LABELS)
        layer = random.choice(_CUSTOMER_LAYERS)

        for item_idx in range(item_count):
            # 最初の party_size 品はドリンク（乾杯）→ 以降はランダム
            if item_idx < party_size:
                category = "ドリンク"
            else:
                category = random.choices(
                    list(_MENU.keys()), weights=[20, 18, 18, 12, 18, 14]
                )[0]
            item_name, base_price = random.choice(_MENU[category])
            quantity = random.choices([1, 2, 3], weights=[72, 22, 6])[0]
            unit_price = int(base_price * random.uniform(0.95, 1.08) / 10) * 10
            rows.append({
                "store_name": store_name,
                "shop_code": store_name[:2],
                "receipt_no": f"D{receipt_no:05d}",
                "visit_time": visit_time,
                "leave_time": visit_time + pd.Timedelta(minutes=stay_minutes),
                "order_time": visit_time + pd.Timedelta(minutes=random.randint(0, max(1, stay_minutes - 5))),
                "party_size": party_size,
                "customer_layer": layer,
                "item_name": item_name,
                "quantity": quantity,
                "unit_price": unit_price,
                "line_total": quantity * unit_price,
                "temp_max": random.randint(22, 32),
                "temp_mean": random.randint(18, 28),
                "precip": 0.0 if random.random() > 0.25 else round(random.uniform(0.5, 12.0), 1),
                "weather_label": weather,
                "visit_key": visit_key,
                "category": category,
                "hour": hour,
                "dow": visit_time.dayofweek,
                "date": str(visit_time.date()),
                "year_month": visit_time.strftime("%Y-%m"),
            })

    df = pd.DataFrame(rows)

    # 月・店舗の絞り込み（UI の選択を反映）
    if months:
        df = df[df["year_month"].isin(months)]
    names = _store_names_from_ids(store_ids)
    if names:
        df = df[df["store_name"].isin(names)]

    return df.reset_index(drop=True)
