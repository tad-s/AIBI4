"""PoC ドリルダウン集計。

- カテゴリペア/カテゴリ3連鎖 → それを構成する具体的な商品ペア/商品3連鎖の内訳
- PoC①の商品 → その商品の時間帯別 数量

exclude=True で上位3品(サイコロステ/フライドポテト/肉豆腐)を外した内訳＝
「上位3品除く」版カードからのドリルと整合させる。
重い連鎖マップ(_consecutive/_consecutive3)は (df, exclude) 単位でキャッシュ。
"""
from __future__ import annotations

import pandas as pd

from poc.analyses import TOP3_EXCLUDE, _consecutive, _consecutive3, _party2, _visits_ge15

_CACHE: dict = {"_dfid": None}


def _entry(df: pd.DataFrame, exclude: bool) -> dict:
    if _CACHE.get("_dfid") != id(df):
        _CACHE.clear()
        _CACHE["_dfid"] = id(df)
    key = "ex" if exclude else "full"
    if key not in _CACHE:
        base = df[~df["item_name"].isin(TOP3_EXCLUDE)] if exclude else df
        _CACHE[key] = {"df": base.reset_index(drop=True),
                       "catmap": dict(zip(base["item_name"], base["category"])),
                       "pair": None, "seq3": None}
    return _CACHE[key]


def _pop_cat(df: pd.DataFrame) -> pd.DataFrame:
    # カテゴリ継続(④/⑥)・PoC①と同じ母集団: 2組以上かつ15品以上
    return _visits_ge15(_party2(df))


def item_pairs_for_category_pair(df, cat_a, cat_b, exclude=False, top=20) -> list[dict]:
    e = _entry(df, exclude)
    if e["pair"] is None:
        cnt, tbl, _ = _consecutive(_pop_cat(e["df"]), "item_name")
        e["pair"] = (cnt, tbl)
    cnt, tbl = e["pair"]
    catmap = e["catmap"]
    rows = [{"商品ペア": f"{x} → {y}", "前(item_a)": x, "次(item_b)": y,
             "連続注文数": c, "卓数": len(tbl[(x, y)])}
            for (x, y), c in cnt.items()
            if catmap.get(x) == cat_a and catmap.get(y) == cat_b]
    rows.sort(key=lambda r: (-r["卓数"], -r["連続注文数"]))
    return rows[:top]


def item_triples_for_category_seq(df, a, b, c, exclude=False, top=20) -> list[dict]:
    e = _entry(df, exclude)
    if e["seq3"] is None:
        cnt, tbl, _ = _consecutive3(_pop_cat(e["df"]), "item_name")
        e["seq3"] = (cnt, tbl)
    cnt, tbl = e["seq3"]
    catmap = e["catmap"]
    rows = [{"商品3連鎖": f"{x} → {y} → {z}", "連続注文数": v, "卓数": len(tbl[(x, y, z)])}
            for (x, y, z), v in cnt.items()
            if catmap.get(x) == a and catmap.get(y) == b and catmap.get(z) == c]
    rows.sort(key=lambda r: (-r["卓数"], -r["連続注文数"]))
    return rows[:top]


def item_hours(df, item, exclude=False) -> dict:
    """PoC①と同じ母集団での、商品の時間帯(注文時刻)別 数量・卓数。"""
    base = df[~df["item_name"].isin(TOP3_EXCLUDE)] if exclude else df
    d = _pop_cat(base)
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
