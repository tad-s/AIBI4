"""DuckDB セッションの items から、分析用の伝票粒度 DataFrame を構築する。

注文順序系の分析のため、商品リスト・カテゴリリストは order_time 昇順で並べる。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from core.duck import Session


def build_order_df(session: Session, where: str = "") -> pd.DataFrame | None:
    # items テーブルが未作成（ロード0件）の場合は None
    exists = session.query(
        "SELECT count(*) AS n FROM information_schema.tables WHERE table_name = 'items'"
    )["n"].iloc[0]
    if not exists:
        return None
    items = session.query(
        f"SELECT * FROM items{where} ORDER BY visit_key, order_time NULLS LAST, item_name"
    )
    if items.empty:
        return None

    items["line_total"] = pd.to_numeric(items["line_total"], errors="coerce").fillna(0)
    items["visit_time"] = pd.to_datetime(items["visit_time"], errors="coerce")
    items["leave_time"] = pd.to_datetime(items["leave_time"], errors="coerce")
    items["is_drink"] = (items["category"] == "ドリンク").astype(int)

    def agg(g: pd.DataFrame) -> pd.Series:
        names = [str(x) for x in g["item_name"].tolist() if pd.notna(x)]
        cats = [str(x) for x in g["category"].tolist() if pd.notna(x)]
        vt = g["visit_time"].iloc[0]
        lt = g["leave_time"].iloc[0]
        stay = np.nan
        if pd.notna(vt) and pd.notna(lt):
            stay = max(0.0, min((lt - vt).total_seconds() / 60.0, 480.0))
        return pd.Series({
            "商品リスト": names,
            "カテゴリリスト": cats,
            "商品数": len(names),
            "客単価": float(g["line_total"].sum()),
            "時間帯": int(g["hour"].iloc[0]) if pd.notna(g["hour"].iloc[0]) else None,
            "曜日": int(g["dow"].iloc[0]) if pd.notna(g["dow"].iloc[0]) else None,
            "客層": g["customer_layer"].iloc[0],
            "店舗名": g["store_name"].iloc[0],
            "人数": int(g["party_size"].max()) if pd.notna(g["party_size"].max()) else None,
            "滞在時間": stay,
            "ドリンク数": int(g["is_drink"].sum()),
        })

    odf = items.groupby("visit_key", sort=False).apply(agg, include_groups=False).reset_index()
    odf = odf[odf["客単価"] > 0].reset_index(drop=True)
    return odf if len(odf) else None
