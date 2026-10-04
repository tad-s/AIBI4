"""DuckDB セッション管理。

セッションごとにインメモリ DuckDB を持ち、`items`（商品明細粒度）と
`orders`（伝票粒度）の2テーブルを構築する。分析クエリはこの2テーブルに対して実行する。
"""
from __future__ import annotations

import time
import uuid

import duckdb
import pandas as pd

from core.config import settings

# ── orders ビュー（伝票粒度）を items から集計する SQL ──
_ORDERS_SQL = """
CREATE OR REPLACE TABLE orders AS
SELECT
    visit_key,
    any_value(store_name)      AS store_name,
    any_value(customer_layer)  AS customer_layer,
    max(party_size)            AS party_size,
    min(visit_time)            AS visit_time,
    any_value(leave_time)      AS leave_time,
    any_value(hour)            AS hour,
    any_value(dow)             AS dow,
    any_value(date)            AS date,
    any_value(year_month)      AS year_month,
    any_value(weather_label)   AS weather_label,
    any_value(temp_max)        AS temp_max,
    any_value(temp_mean)       AS temp_mean,
    any_value(precip)          AS precip,
    sum(line_total)            AS order_total,
    sum(quantity)              AS item_count,
    sum(CASE WHEN category = 'ドリンク' THEN quantity ELSE 0 END) AS drink_count,
    CASE
        WHEN any_value(leave_time) IS NOT NULL AND min(visit_time) IS NOT NULL
        THEN least(greatest(date_diff('minute', min(visit_time), any_value(leave_time)), 0), 480)
        ELSE NULL
    END AS stay_minutes
FROM items
GROUP BY visit_key
HAVING sum(line_total) > 0
"""


class Session:
    def __init__(self, dataset: str):
        self.con = duckdb.connect(":memory:")
        self.dataset = dataset
        self.created_at = time.time()
        self.meta: dict = {}

    def load(self, items_df: pd.DataFrame) -> None:
        self.con.register("items_src", items_df)
        self.con.execute("CREATE OR REPLACE TABLE items AS SELECT * FROM items_src")
        self.con.unregister("items_src")
        self.con.execute(_ORDERS_SQL)
        self._compute_meta(items_df)

    def _compute_meta(self, items_df: pd.DataFrame) -> None:
        orders_n = self.con.execute("SELECT count(*) FROM orders").fetchone()[0]
        stores = self.con.execute(
            "SELECT DISTINCT store_name FROM items WHERE store_name IS NOT NULL ORDER BY 1"
        ).df()["store_name"].tolist()
        months = self.con.execute(
            "SELECT DISTINCT year_month FROM items ORDER BY 1"
        ).df()["year_month"].tolist()
        cats = self.con.execute(
            "SELECT DISTINCT category FROM items ORDER BY 1"
        ).df()["category"].tolist()
        has_weather = bool(
            self.con.execute("SELECT count(weather_label) FROM items").fetchone()[0]
        )
        self.meta = {
            "item_rows": int(len(items_df)),
            "order_rows": int(orders_n),
            "stores": stores,
            "months": months,
            "categories": cats,
            "has_weather": has_weather,
        }

    def query(self, sql: str, params: list | None = None) -> pd.DataFrame:
        return self.con.execute(sql, params or []).df()


class SessionStore:
    def __init__(self):
        self._sessions: dict[str, Session] = {}

    def _cleanup(self):
        now = time.time()
        expired = [
            k for k, s in self._sessions.items()
            if now - s.created_at > settings.SESSION_TTL_SEC
        ]
        for k in expired:
            try:
                self._sessions[k].con.close()
            except Exception:
                pass
            del self._sessions[k]

    def create(self, dataset: str) -> str:
        self._cleanup()
        sid = str(uuid.uuid4())
        self._sessions[sid] = Session(dataset)
        return sid

    def get(self, sid: str) -> Session | None:
        return self._sessions.get(sid)


store = SessionStore()
