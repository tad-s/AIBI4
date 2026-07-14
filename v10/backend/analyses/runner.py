"""全分析の実行（グローバルフィルタ適用 → 伝票粒度DF構築 → ①〜⑫）。"""
from __future__ import annotations

from core.duck import Session
from analyses.base import run_base
from analyses.order_df import build_order_df
from analyses.order_flow import run_order_flow
from semantic.engine import _build_where
from semantic.query import Filters


def run_all(session: Session, filters: Filters | None = None) -> dict:
    where = _build_where(filters, "items") if filters is not None else ""
    odf = build_order_df(session, where)
    if odf is None or odf.empty:
        return {"base": [], "order_flow": [], "message": "該当データがありません。"}
    return {"base": run_base(odf), "order_flow": run_order_flow(odf), "message": ""}
