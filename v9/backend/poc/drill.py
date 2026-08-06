"""PoC ドリルダウン集計。

- カテゴリペア/カテゴリ3連鎖 → それを構成する具体的な商品ペア/商品3連鎖の内訳
- PoC①の商品 → その商品の時間帯別 数量

重い連鎖マップ(_consecutive/_consecutive3)は df 単位でキャッシュ（df再構築で自動失効）。
"""
from __future__ import annotations

import pandas as pd

from poc.analyses import _consecutive, _consecutive3, _party2, _visits_ge15

_CACHE: dict = {}


def _maps(df: pd.DataFrame) -> dict:
    if _CACHE.get("_key") != id(df):
        _CACHE.clear()
        _CACHE["_key"] = id(df)
        _CACHE["catmap"] = dict(zip(df["item_name"], df["category"]))
    return _CACHE


def _pop_cat(df: pd.DataFrame) -> pd.DataFrame:
    # カテゴリ継続(④/⑥)と同じ母集団: 2組以上かつ15品以上
    return _visits_ge15(_party2(df))


def item_pairs_for_category_pair(df: pd.DataFrame, cat_a: str, cat_b: str, top: int = 20) -> list[dict]:
    m = _maps(df)
    if "pair" not in m:
        cnt, tbl, _ = _consecutive(_pop_cat(df), "item_name")
        m["pair"] = (cnt, tbl)
    cnt, tbl = m["pair"]
    catmap = m["catmap"]
    rows = [{"商品ペア": f"{x} → {y}", "前(item_a)": x, "次(item_b)": y,
             "連続注文数": c, "卓数": len(tbl[(x, y)])}
            for (x, y), c in cnt.items()
            if catmap.get(x) == cat_a and catmap.get(y) == cat_b]
    rows.sort(key=lambda r: (-r["卓数"], -r["連続注文数"]))
    return rows[:top]


def item_triples_for_category_seq(df: pd.DataFrame, a: str, b: str, c: str, top: int = 20) -> list[dict]:
    m = _maps(df)
    if "seq3" not in m:
        cnt, tbl, _ = _consecutive3(_pop_cat(df), "item_name")
        m["seq3"] = (cnt, tbl)
    cnt, tbl = m["seq3"]
    catmap = m["catmap"]
    rows = [{"商品3連鎖": f"{x} → {y} → {z}", "連続注文数": v, "卓数": len(tbl[(x, y, z)])}
            for (x, y, z), v in cnt.items()
            if catmap.get(x) == a and catmap.get(y) == b and catmap.get(z) == c]
    rows.sort(key=lambda r: (-r["卓数"], -r["連続注文数"]))
    return rows[:top]


def item_hours(df: pd.DataFrame, item: str) -> dict:
    """PoC①と同じ母集団での、商品の時間帯(注文時刻)別 数量・卓数。"""
    d = _pop_cat(df)
    sub = d[d["item_name"] == item].copy()
    if not len(sub):
        return {"item": item, "total_qty": 0, "hours": []}
    dt = pd.to_datetime(sub["ordered_at"], errors="coerce")
    if getattr(dt.dt, "tz", None) is not None:          # Supabase(+00:00)→JST
        dt = dt.dt.tz_convert("Asia/Tokyo").dt.tz_localize(None)
    sub["hour"] = dt.dt.hour
    g = sub.dropna(subset=["hour"]).groupby(sub["hour"].astype("Int64"))
    agg = g.agg(数量=("quantity", "sum"), 卓数=("visit_id", "nunique"))
    hours = [{"時間帯": f"{int(h)}時", "hour": int(h),
              "数量": int(agg.loc[h, "数量"]), "卓数": int(agg.loc[h, "卓数"])}
             for h in agg.index]
    hours.sort(key=lambda r: r["hour"])
    return {"item": item, "total_qty": int(sub["quantity"].sum()), "hours": hours}
