"""外部接続なしでV12を触るためのデモデータ生成。"""
from __future__ import annotations

import random

import pandas as pd


def build_demo_items_df(seed: int = 12, orders: int = 520) -> pd.DataFrame:
    random.seed(seed)
    stores = ["新宿店", "渋谷店", "神田店", "横浜店", "千葉店", "柏店"]
    customer_layers = ["会社員", "学生", "家族", "シニア", "少人数宴会"]
    weather_labels = ["晴れ", "曇り", "雨"]
    menu = {
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

    rows: list[dict] = []
    for receipt_no in range(orders):
        store_name = random.choice(stores)
        day = random.randint(1, 28)
        hour = random.choices([11, 12, 17, 18, 19, 20, 21, 22], weights=[2, 3, 6, 10, 12, 10, 7, 3])[0]
        visit_time = pd.Timestamp(2025, random.choice([9, 10]), day, hour, random.choice([0, 15, 30, 45]))
        party_size = random.choices([1, 2, 3, 4, 5, 6], weights=[12, 36, 20, 18, 8, 6])[0]
        item_count = random.randint(max(1, party_size), max(3, party_size * 4))
        stay_minutes = random.randint(35, 150)
        visit_key = f"{visit_time.strftime('%Y%m%d%H%M%S')}_D{receipt_no:05d}"

        for item_idx in range(item_count):
            if item_idx < party_size:
                category = "ドリンク"
            else:
                category = random.choices(
                    list(menu.keys()),
                    weights=[20, 18, 18, 12, 18, 14],
                )[0]
            item_name, base_price = random.choice(menu[category])
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
                "customer_layer": random.choice(customer_layers),
                "item_name": item_name,
                "quantity": quantity,
                "unit_price": unit_price,
                "line_total": quantity * unit_price,
                "temp_max": random.randint(22, 32),
                "temp_mean": random.randint(18, 28),
                "precip": 0 if random.random() > 0.25 else round(random.uniform(0.5, 12.0), 1),
                "weather_label": random.choice(weather_labels),
                "visit_key": visit_key,
                "category": category,
                "hour": hour,
                "dow": visit_time.dayofweek,
                "date": str(visit_time.date()),
                "year_month": visit_time.strftime("%Y-%m"),
            })

    return pd.DataFrame(rows)
