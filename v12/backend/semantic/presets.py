"""デフォルトダッシュボードのプリセット（QuerySpec の組み合わせ）。

BIツールの「初期ダッシュボード」に相当。データ投入直後に自動表示する。
"""
from __future__ import annotations

# KPI スコアカード（軸なし = 全体集計）
KPI_SPECS = [
    {"metric": "revenue",     "chart_type": "kpi"},
    {"metric": "order_count", "chart_type": "kpi"},
    {"metric": "avg_spend",   "chart_type": "kpi"},
    {"metric": "avg_items",   "chart_type": "kpi"},
    {"metric": "avg_party",   "chart_type": "kpi"},
    {"metric": "avg_stay",    "chart_type": "kpi"},
]

# ダッシュボードのチャートタイル
TILE_SPECS = [
    {
        "metric": "revenue", "dimensions": ["month"],
        "chart_type": "line", "sort": "dim_asc", "limit": 24,
        "title": "月次売上推移",
    },
    {
        "metric": "revenue", "dimensions": ["category"],
        "chart_type": "pie", "sort": "value_desc", "limit": 10,
        "title": "カテゴリ別 売上構成",
    },
    {
        "metric": "avg_spend", "dimensions": ["hour"],
        "chart_type": "bar", "sort": "dim_asc", "limit": 24,
        "title": "時間帯別 客単価",
    },
    {
        "metric": "revenue", "dimensions": ["store"],
        "chart_type": "bar", "sort": "value_desc", "limit": 15,
        "title": "店舗別 売上ランキング",
    },
    {
        "metric": "order_count", "dimensions": ["dow"],
        "chart_type": "bar", "sort": "dim_asc", "limit": 7,
        "title": "曜日別 注文数",
    },
    {
        "metric": "avg_spend", "dimensions": ["weather"],
        "chart_type": "bar", "sort": "value_desc", "limit": 10,
        "title": "天気別 客単価",
    },
]
