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
    synonyms: tuple[str, ...] = ()   # 業務用語・言い換え（LLM の写像精度向上用）


@dataclass(frozen=True)
class Dimension:
    id: str
    label: str
    sql: str
    views: tuple[str, ...]           # 利用可能な base view
    kind: str = "cat"                # "cat" | "time" | "num"
    description: str = ""
    labels: dict | None = None       # 値 → 表示ラベル（曜日など）
    synonyms: tuple[str, ...] = ()   # 業務用語・言い換え（LLM の写像精度向上用）


# ───────────────────────── 指標 ─────────────────────────
METRICS: dict[str, Metric] = {m.id: m for m in [
    Metric("revenue",     "売上",         "items",  "sum(line_total)",
           "円", "yen", "税込の売上金額合計",
           synonyms=("売上高", "売り上げ", "総売上", "売上金額", "収益", "sales", "revenue")),
    Metric("quantity",    "販売点数",     "items",  "sum(quantity)",
           "点", "int", "販売された商品の数量合計",
           synonyms=("販売数", "数量", "個数", "出数", "販売個数", "点数", "quantity")),
    Metric("order_count", "注文数",       "orders", "count(*)",
           "件", "int", "伝票（来店）数＝来店組数",
           synonyms=("伝票数", "来店数", "来店組数", "組数", "客組数", "会計数", "オーダー数", "件数", "orders")),
    Metric("visitors",    "来店人数",     "orders", "sum(party_size)",
           "人", "int", "延べ来店客数（1来店の人数を合計）",
           synonyms=("来店客数", "客数", "総来店人数", "延べ人数", "visitors", "headcount")),
    Metric("avg_spend",   "客単価",       "orders", "avg(order_total)",
           "円", "yen", "1伝票あたりの平均支払額",
           synonyms=("客単価", "平均客単価", "1組あたり単価", "伝票単価", "平均会計額", "average check")),
    Metric("avg_party",   "平均人数",     "orders", "avg(party_size)",
           "人", "float1", "1来店グループの平均人数",
           synonyms=("平均組人数", "平均来店人数", "1組の人数", "グループ人数")),
    Metric("per_person",  "一人単価",     "orders", "sum(order_total)/nullif(sum(party_size),0)",
           "円", "yen", "1人あたりの平均支払額",
           synonyms=("一人あたり単価", "1人単価", "人単価", "per person")),
    Metric("avg_stay",    "平均滞在時間", "orders", "avg(stay_minutes)",
           "分", "float1", "来店〜退店の平均滞在分数",
           synonyms=("滞在時間", "滞在", "在店時間", "回転時間", "stay")),
    Metric("avg_items",   "平均注文点数", "orders", "avg(item_count)",
           "点", "float1", "1伝票あたりの平均商品点数",
           synonyms=("平均品数", "1組の注文点数", "平均オーダー点数", "注文点数")),
    Metric("drink_ratio", "ドリンク比率", "orders", "sum(drink_count)/nullif(sum(item_count),0)",
           "%", "pct", "全注文点数に占めるドリンクの割合",
           synonyms=("ドリンク割合", "飲み物比率", "drink ratio")),
]}

# ───────────────────────── 軸 ─────────────────────────
_DOW_LABELS = {0: "月", 1: "火", 2: "水", 3: "木", 4: "金", 5: "土", 6: "日"}

DIMENSIONS: dict[str, Dimension] = {d.id: d for d in [
    Dimension("store",          "店舗",       "store_name",     ("items", "orders"), "cat",
              synonyms=("店", "店別", "店舗別", "支店", "拠点", "shop", "store")),
    Dimension("category",       "商品カテゴリ", "category",       ("items",),          "cat",
              synonyms=("カテゴリ", "分類", "商品分類", "ジャンル", "メニュー分類", "category")),
    Dimension("item",           "商品",       "item_name",      ("items",),          "cat",
              synonyms=("メニュー", "品目", "商品名", "アイテム", "item", "product")),
    Dimension("hour",           "時間帯",     "hour",           ("items", "orders"), "time",
              synonyms=("時間", "時間別", "時刻", "何時", "hour", "time of day")),
    Dimension("dow",            "曜日",       "dow",            ("items", "orders"), "time",
              labels=_DOW_LABELS,
              synonyms=("曜日別", "何曜日", "day of week", "weekday")),
    Dimension("customer_layer", "客層",       "customer_layer", ("items", "orders"), "cat",
              synonyms=("顧客層", "客タイプ", "顧客タイプ", "セグメント", "属性", "segment")),
    Dimension("month",          "月",         "year_month",     ("items", "orders"), "time",
              synonyms=("月別", "月次", "各月", "月ごと", "month")),
    Dimension("date",           "日付",       "date",           ("items", "orders"), "time",
              synonyms=("日別", "日次", "日ごと", "デイリー", "date", "daily")),
    Dimension("weather",        "天気",       "weather_label",  ("items", "orders"), "cat",
              synonyms=("天候", "気象", "晴れ雨", "weather")),
]}


def metric_catalog() -> list[dict]:
    return [
        {"id": m.id, "label": m.label, "unit": m.unit, "view": m.view,
         "description": m.description, "synonyms": list(m.synonyms)}
        for m in METRICS.values()
    ]


def dimension_catalog() -> list[dict]:
    return [
        {"id": d.id, "label": d.label, "kind": d.kind, "views": list(d.views),
         "synonyms": list(d.synonyms)}
        for d in DIMENSIONS.values()
    ]
