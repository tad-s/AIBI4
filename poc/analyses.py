"""テング池袋東口店 レコメンドPoC — 4分析。

入力: poc/data/poc_base.parquet（build_base_table.py で生成、除外適用済み・order粒度）
1来店ID = visit_id（源泉の UUID をそのまま使用。都度キー生成はしない）

定義（要件書）:
  #1 注文総数が多い卓の商品TOP10  … 母集団[party>=2 & 来店合計数量>=15]、商品を合計数量で順位、フード/ドリンク別
  #2 同時注文ペア TOP10           … 母集団[party>=2]、同一order_id、無向ペア、drink-only除外、両方drinkは除外
  #3 連続注文ペア TOP10           … 母集団[party>=2]、隣接order_seq の A(前)→B(次)、有向、>=10卓
  #4 注文継続の組み合わせ 各Top5  … 母集団[party>=2 & >=15品]（①〜③と同一母集団）、連続ペアをFD組合せ別/カテゴリ別に
"""
from __future__ import annotations

import os
from collections import Counter, defaultdict
from itertools import combinations

import pandas as pd

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "poc_base.parquet")
MIN_TABLES = 10  # 「10卓以上」


def load() -> pd.DataFrame:
    df = pd.read_parquet(BASE)
    df["order_seq"] = pd.to_numeric(df["order_seq"], errors="coerce")
    return df


def _party2(df: pd.DataFrame) -> pd.DataFrame:
    """2組以上（1人客除外）= party_size>=2。"""
    return df[df["party_size"] >= 2]


def _visits_ge15(df: pd.DataFrame) -> pd.DataFrame:
    """来店合計数量>=15 の来店だけに絞る。"""
    vq = df.groupby("visit_id")["quantity"].sum()
    keep = vq[vq >= 15].index
    return df[df["visit_id"].isin(keep)]


# ── #1 注文総数が多い卓の商品TOP10（フード/ドリンク別）──
def analysis1(df: pd.DataFrame) -> dict:
    d = _visits_ge15(_party2(df))
    g = (d.groupby(["item_name", "fd", "category"])
           .agg(数量=("quantity", "sum"), 卓数=("visit_id", "nunique"))
           .reset_index())
    overall = g.sort_values("数量", ascending=False).head(10)
    drink = g[g["fd"] == "ドリンク"].sort_values("数量", ascending=False).head(10)
    food = g[g["fd"] == "フード"].sort_values("数量", ascending=False).head(10)
    return {"母集団_来店数": d["visit_id"].nunique(), "overall": overall, "drink": drink, "food": food}


# ── #2 同時注文ペア TOP10（同一order内・drink-only除外・両drink除外）──
def analysis2(df: pd.DataFrame) -> pd.DataFrame:
    d = _party2(df)
    fdmap = dict(zip(d["item_name"], d["fd"]))
    og = d.groupby("order_id").agg(
        items=("item_name", lambda s: list(dict.fromkeys(s))),
        visit_id=("visit_id", "first"),
    )
    cnt: Counter = Counter()             # 共起オーダー数
    tbl: defaultdict = defaultdict(set)  # 卓数
    for row in og.itertuples():
        names = row.items
        if not any(fdmap[n] == "フード" for n in names):
            continue  # ドリンクのみのオーダーは除外
        for a, b in combinations(sorted(set(names)), 2):
            if fdmap[a] == "ドリンク" and fdmap[b] == "ドリンク":
                continue  # 両方ドリンクは対象外（drink×food, food×foodのみ）
            cnt[(a, b)] += 1
            tbl[(a, b)].add(row.visit_id)
    rows = [{"商品A": a, "商品B": b, "組合せ": f"{fdmap[a]}×{fdmap[b]}",
             "共起オーダー数": c, "卓数": len(tbl[(a, b)])} for (a, b), c in cnt.items()]
    return (pd.DataFrame(rows).sort_values(["共起オーダー数", "卓数"], ascending=False)
            .head(10).reset_index(drop=True))


def _consecutive_pairs(d: pd.DataFrame, level: str):
    """隣接オーダー間の有向ペア A(前)→B(次)。level='item' or 'category'。

    戻り: cnt(出現回数), tbl(卓集合), fd(要素→FD)
    """
    col = "item_name" if level == "item" else "category"
    cnt: Counter = Counter()
    tbl: defaultdict = defaultdict(set)
    fd: dict = dict(zip(d[col], d["fd"]))  # 要素→FD（カテゴリ粒度では category→代表FD）

    # (visit_id, order_seq) ごとの重複なし要素リスト
    og = (d.sort_values(["visit_id", "order_seq"])
            .groupby(["visit_id", "order_seq"])[col]
            .agg(lambda s: list(dict.fromkeys(s))))
    for vid, sub in og.groupby(level=0):
        vals = sub.droplevel(0).sort_index().tolist()  # order_seq 昇順の要素リスト群
        for i in range(len(vals) - 1):
            prev, nxt = vals[i], vals[i + 1]
            for a in prev:
                for b in nxt:
                    if a == b:
                        continue  # 2商品のペアのみ（同一要素の連続は除外）
                    cnt[(a, b)] += 1
                    tbl[(a, b)].add(vid)
    return cnt, tbl, fd


# ── #3 連続注文ペア TOP10（有向・全パターン・>=10卓）──
def analysis3(df: pd.DataFrame) -> pd.DataFrame:
    d = _party2(df)
    cnt, tbl, fd = _consecutive_pairs(d, "item")
    rows = [{"前→次": f"{a} → {b}", "組合せ": f"{fd[a]}→{fd[b]}",
             "出現回数": c, "卓数": len(tbl[(a, b)])}
            for (a, b), c in cnt.items() if len(tbl[(a, b)]) >= MIN_TABLES]
    return (pd.DataFrame(rows).sort_values(["卓数", "出現回数"], ascending=False)
            .head(10).reset_index(drop=True))


# ── #4 注文継続につながる組み合わせ 各Top5（FD組合せ別・カテゴリ別）──
def analysis4(df: pd.DataFrame) -> dict:
    d = _visits_ge15(_party2(df))   # ①〜③と同一母集団（party>=2 & >=15品）
    out: dict = {"母集団_来店数": d["visit_id"].nunique()}

    # 商品単位: 連続ペアを FD 組合せ別に Top5
    cnt, tbl, fd = _consecutive_pairs(d, "item")
    rows = [{"前→次": f"{a} → {b}", "fa": fd[a], "fb": fd[b],
             "出現回数": c, "卓数": len(tbl[(a, b)])}
            for (a, b), c in cnt.items() if len(tbl[(a, b)]) >= MIN_TABLES]
    ip = pd.DataFrame(rows)

    def bucket(dfp, kind):
        if dfp.empty:
            return dfp
        if kind == "FF":
            m = (dfp["fa"] == "フード") & (dfp["fb"] == "フード")
        elif kind == "DD":
            m = (dfp["fa"] == "ドリンク") & (dfp["fb"] == "ドリンク")
        else:  # FD (どちらか一方がドリンク)
            m = (dfp["fa"] != dfp["fb"])
        return (dfp[m].sort_values(["卓数", "出現回数"], ascending=False)
                .head(5)[["前→次", "出現回数", "卓数"]].reset_index(drop=True))

    out["item_FF"] = bucket(ip, "FF")
    out["item_DD"] = bucket(ip, "DD")
    out["item_FD"] = bucket(ip, "FD")

    # カテゴリ単位: 連続ペア Top5（例: ドリンク→揚げ物 等）
    ccnt, ctbl, cfd = _consecutive_pairs(d, "category")
    crows = [{"カテゴリ 前→次": f"{a} → {b}", "出現回数": c, "卓数": len(ctbl[(a, b)])}
             for (a, b), c in ccnt.items() if len(ctbl[(a, b)]) >= MIN_TABLES]
    out["category_top"] = (pd.DataFrame(crows).sort_values(["卓数", "出現回数"], ascending=False)
                           .head(10).reset_index(drop=True))
    return out


def _show(title, df):
    print(f"\n── {title} ──")
    print(df.to_string(index=False) if len(df) else "  (該当なし)")


def main():
    df = load()
    print(f"PoC母集団(基礎テーブル): 明細{len(df):,} / 来店{df['visit_id'].nunique():,} / "
          f"オーダー{df['order_id'].nunique():,}")

    a1 = analysis1(df)
    print(f"\n【#1 注文総数が多い卓の商品TOP10】 母集団来店={a1['母集団_来店数']:,}（party>=2 & 15品以上）")
    _show("全体 TOP10（合計数量）", a1["overall"][["item_name", "fd", "category", "数量", "卓数"]])
    _show("ドリンク TOP10", a1["drink"][["item_name", "category", "数量", "卓数"]])
    _show("フード TOP10", a1["food"][["item_name", "category", "数量", "卓数"]])

    print("\n\n【#2 同時注文ペア TOP10】（同一オーダー内・drink-only除外・両drink除外, party>=2）")
    _show("同時注文ペア", analysis2(df))

    print("\n\n【#3 連続注文ペア TOP10】（隣接オーダー A→B・有向・全パターン・>=10卓, party>=2）")
    _show("連続注文ペア", analysis3(df))

    a4 = analysis4(df)
    print(f"\n\n【#4 注文継続につながる組み合わせ 各Top5】 母集団来店={a4['母集団_来店数']:,}（party>=2 & 15品以上, >=10卓）")
    _show("フード→フード Top5", a4["item_FF"])
    _show("ドリンク→ドリンク Top5", a4["item_DD"])
    _show("フード↔ドリンク Top5", a4["item_FD"])
    _show("カテゴリ連続ペア Top10", a4["category_top"])


if __name__ == "__main__":
    main()
