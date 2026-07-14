"""セマンティック層 — 指標(metric)と軸(dimension)の定義。

LLM も UI も「生SQL」ではなく、この定義済みの指標・軸を組み合わせて分析を表現する。
これにより集計は決定論的・テスト可能・監査可能になる。

base view の考え方:
- items  : 商品明細粒度（1商品=1行）。売上・数量やカテゴリ/商品別の内訳に使う。
- orders : 伝票粒度（1来店=1行）。客単価・注文数・人数・滞在など「1注文あたり」の指標に使う。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Metric:
    id: str
    label: str
    view: str            # "items" | "orders"
    sql: str             # 集計式
    unit: str            # "円" | "件" | "点" | "分" | "%" | "人" | ""
    fmt: str             # "int" | "yen" | "pct" | "float1"
    description: str = ""


@dataclass(frozen=True)
class Dimension:
    id: str
    label: str
    sql: str
    views: tuple[str, ...]           # 利用可能な base view
    kind: str = "cat"                # "cat" | "time" | "num"
    description: str = ""
    labels: dict | None = None       # 値 → 表示ラベル（曜日など）


# ───────────────────────── 指標 ─────────────────────────
METRICS: dict[str, Metric] = {m.id: m for m in [
    Metric("revenue",     "売上",         "items",  "sum(line_total)",
           "円", "yen", "税込の売上金額合計"),
    Metric("quantity",    "販売点数",     "items",  "sum(quantity)",
           "点", "int", "販売された商品の数量合計"),
    Metric("order_count", "注文数",       "orders", "count(*)",
           "件", "int", "伝票（来店）数"),
    Metric("avg_spend",   "客単価",       "orders", "avg(order_total)",
           "円", "yen", "1伝票あたりの平均支払額"),
    Metric("avg_party",   "平均人数",     "orders", "avg(party_size)",
           "人", "float1", "1来店グループの平均人数"),
    Metric("per_person",  "一人単価",     "orders", "sum(order_total)/nullif(sum(party_size),0)",
           "円", "yen", "1人あたりの平均支払額"),
    Metric("avg_stay",    "平均滞在時間", "orders", "avg(stay_minutes)",
           "分", "float1", "来店〜退店の平均滞在分数"),
    Metric("avg_items",   "平均注文点数", "orders", "avg(item_count)",
           "点", "float1", "1伝票あたりの平均商品点数"),
    Metric("drink_ratio", "ドリンク比率", "orders", "sum(drink_count)/nullif(sum(item_count),0)",
           "%", "pct", "全注文点数に占めるドリンクの割合"),
]}

# ───────────────────────── 軸 ─────────────────────────
_DOW_LABELS = {0: "月", 1: "火", 2: "水", 3: "木", 4: "金", 5: "土", 6: "日"}

DIMENSIONS: dict[str, Dimension] = {d.id: d for d in [
    Dimension("store",          "店舗",       "store_name",     ("items", "orders"), "cat"),
    Dimension("category",       "商品カテゴリ", "category",       ("items",),          "cat"),
    Dimension("item",           "商品",       "item_name",      ("items",),          "cat"),
    Dimension("hour",           "時間帯",     "hour",           ("items", "orders"), "time"),
    Dimension("dow",            "曜日",       "dow",            ("items", "orders"), "time",
              labels=_DOW_LABELS),
    Dimension("customer_layer", "客層",       "customer_layer", ("items", "orders"), "cat"),
    Dimension("month",          "月",         "year_month",     ("items", "orders"), "time"),
    Dimension("date",           "日付",       "date",           ("items", "orders"), "time"),
    Dimension("weather",        "天気",       "weather_label",  ("items", "orders"), "cat"),
]}


def metric_catalog() -> list[dict]:
    return [
        {"id": m.id, "label": m.label, "unit": m.unit, "view": m.view, "description": m.description}
        for m in METRICS.values()
    ]


def dimension_catalog() -> list[dict]:
    return [
        {"id": d.id, "label": d.label, "kind": d.kind, "views": list(d.views)}
        for d in DIMENSIONS.values()
    ]
