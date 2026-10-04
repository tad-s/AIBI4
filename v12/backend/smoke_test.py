"""外部サービス不要のスモークテスト（DuckDB エンジンの検証）。"""
import pandas as pd

from core.duck import store
from semantic import engine, presets
from semantic.query import QuerySpec

# 合成の商品明細データ
rows = []
import random
random.seed(1)
stores = ["渋谷店", "新宿店", "神田店"]
cats = ["ドリンク", "揚げ物", "串", "海鮮", "軽いつまみ"]
items = {"ドリンク": ["生ビール", "ウーロンハイ"], "揚げ物": ["唐揚げ"], "串": ["焼き鳥"],
         "海鮮": ["刺身盛り"], "軽いつまみ": ["枝豆"]}
for v in range(300):
    st = random.choice(stores)
    n_items = random.randint(1, 6)
    hour = random.choice([17, 18, 19, 20, 21, 22])
    vt = pd.Timestamp(2025, 9, random.randint(1, 28), hour, 0)
    for _ in range(n_items):
        c = random.choice(cats)
        it = random.choice(items[c])
        qty = random.randint(1, 3)
        price = random.choice([390, 490, 590, 680])
        rows.append({
            "store_name": st, "shop_code": "S", "receipt_no": f"R{v}",
            "visit_time": vt, "leave_time": vt + pd.Timedelta(minutes=random.randint(30, 150)),
            "order_time": vt, "party_size": random.randint(1, 4),
            "customer_layer": random.choice(["会社員", "学生", "家族"]),
            "item_name": it, "quantity": qty, "unit_price": price,
            "line_total": qty * price,
            "temp_max": 25, "temp_mean": 22, "precip": 0, "weather_label": random.choice(["晴れ", "雨"]),
            "visit_key": f"{vt.strftime('%Y%m%d%H%M%S')}_R{v}",
            "category": c,
            "hour": hour, "dow": vt.dayofweek, "date": str(vt.date()),
            "year_month": vt.strftime("%Y-%m"),
        })
df = pd.DataFrame(rows)

sid = store.create("izakaya")
session = store.get(sid)
session.load(df)
print("META:", session.meta)

# KPI
print("\n--- KPIs ---")
for raw in presets.KPI_SPECS:
    r = engine.run(session, QuerySpec.model_validate(raw))
    v = r["rows"][0]["value"] if r["rows"] else None
    print(f'  {r["metric"]["label"]}: {v:,.1f} {r["metric"]["unit"]}' if v is not None else r["metric"]["label"])

# タイル
print("\n--- Tiles ---")
for raw in presets.TILE_SPECS:
    r = engine.run(session, QuerySpec.model_validate(raw))
    print(f'  [{r["title"]}] rows={len(r["rows"])} chart={raw["chart_type"]}')

# base 不整合の検証（客単価×カテゴリは SpecError）
print("\n--- 不整合チェック ---")
try:
    engine.run(session, QuerySpec.model_validate({"metric": "avg_spend", "dimensions": ["category"]}))
    print("  NG: エラーが出るべき")
except engine.SpecError as e:
    print(f"  OK SpecError: {e}")

print("\nALL GREEN")
