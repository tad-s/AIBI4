"""T1 PoC 4分析ロジック。"""
from __future__ import annotations

from collections import Counter, defaultdict
from itertools import combinations

import pandas as pd

MIN_TABLES = 10


def party2(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["party_size"] >= 2].copy()


def high_order_visits(df: pd.DataFrame) -> pd.DataFrame:
    visit_qty = df.groupby("visit_id")["quantity"].sum()
    keep = visit_qty[visit_qty >= 15].index
    return df[df["visit_id"].isin(keep)].copy()


def summary(df: pd.DataFrame) -> dict:
    p2 = party2(df)
    high = high_order_visits(p2)
    return {
        "rows": int(len(df)),
        "visits": int(df["visit_id"].nunique()),
        "orders": int(df["order_id"].nunique()),
        "items": int(df["item_name"].nunique()),
        "party2_visits": int(p2["visit_id"].nunique()),
        "high_order_visits": int(high["visit_id"].nunique()),
        "start": str(df["ordered_at"].min()),
        "end": str(df["ordered_at"].max()),
        "fd_counts": df.groupby("fd")["quantity"].sum().sort_values(ascending=False).to_dict(),
        "category_counts": df.groupby("category")["quantity"].sum().sort_values(ascending=False).to_dict(),
    }


def analysis_1_top_items(df: pd.DataFrame) -> dict:
    target = high_order_visits(party2(df))
    grouped = (
        target.groupby(["item_name", "fd", "category"], dropna=False)
        .agg(
            total_qty=("quantity", "sum"),
            table_count=("visit_id", "nunique"),
            order_count=("order_id", "nunique"),
            sales=("line_total", "sum"),
        )
        .reset_index()
    )
    grouped["qty_per_table"] = grouped["total_qty"] / grouped["table_count"].replace(0, pd.NA)
    grouped = grouped.sort_values(["total_qty", "table_count"], ascending=False)

    def records(frame: pd.DataFrame, n: int = 10):
        return frame.head(n).round(2).to_dict("records")

    return {
        "title": "1. 注文総数が多い卓の商品TOP10",
        "population": {"visits": int(target["visit_id"].nunique()), "orders": int(target["order_id"].nunique()), "rows": int(len(target))},
        "overall": records(grouped),
        "drink": records(grouped[grouped["fd"] == "ドリンク"]),
        "food": records(grouped[grouped["fd"] == "フード"]),
        "definition": "2名以上かつ除外後の合計数量15品以上の卓を対象に、商品別合計数量で順位付け。",
    }


def analysis_2_same_order_pairs(df: pd.DataFrame, require_high_order: bool = False) -> dict:
    target = party2(df)
    if require_high_order:
        target = high_order_visits(target)
    pair_count: Counter = Counter()
    table_sets: defaultdict = defaultdict(set)
    fd_map = target.drop_duplicates("item_name").set_index("item_name")["fd"].astype(str).to_dict()
    category_map = target.drop_duplicates("item_name").set_index("item_name")["category"].astype(str).to_dict()

    order_baskets = (
        target.sort_values(["order_seq", "line_index", "ordered_at"])
        .groupby("order_id", sort=False)
        .agg(
            visit_id=("visit_id", "first"),
            items=("item_name", lambda s: list(dict.fromkeys(map(str, s)))),
            has_food=("fd", lambda s: bool((s == "フード").any())),
        )
    )

    for _, order in order_baskets.iterrows():
        if not order["has_food"]:
            continue
        visit_id = str(order["visit_id"])
        for item_a, item_b in combinations(sorted(order["items"]), 2):
            if fd_map.get(item_a) == "ドリンク" and fd_map.get(item_b) == "ドリンク":
                continue
            pair = (item_a, item_b)
            pair_count[pair] += 1
            table_sets[pair].add(visit_id)

    rows = []
    population_tables = max(1, target["visit_id"].nunique())
    for (item_a, item_b), count in pair_count.items():
        table_count = len(table_sets[(item_a, item_b)])
        rows.append({
            "item_a": item_a,
            "item_b": item_b,
            "pair": f"{item_a} × {item_b}",
            "pair_type": f"{fd_map.get(item_a)}×{fd_map.get(item_b)}",
            "category_pair": f"{category_map.get(item_a)}×{category_map.get(item_b)}",
            "co_order_count": int(count),
            "table_count": int(table_count),
            "support_pct": round(table_count / population_tables * 100, 2),
        })
    result = pd.DataFrame(rows)
    if not result.empty:
        result = result.sort_values(["co_order_count", "table_count"], ascending=False).head(10)
    return {
        "title": "2. 同時注文ペア TOP10",
        "population": {"visits": int(target["visit_id"].nunique()), "orders": int(target["order_id"].nunique())},
        "rows": result.to_dict("records") if not result.empty else [],
        "definition": "2名以上。同一order_id内の無向ペア。ドリンクのみオーダー除外、ドリンク×ドリンク除外。",
    }


def consecutive_pairs(df: pd.DataFrame, level: str = "item") -> tuple[Counter, defaultdict, dict, dict]:
    col = "item_name" if level == "item" else "category"
    pair_count: Counter = Counter()
    table_sets: defaultdict = defaultdict(set)
    distinct = df.drop_duplicates(col)
    fd_map = distinct.set_index(col)["fd"].astype(str).to_dict()
    if level == "category":
        category_map = {str(value): str(value) for value in distinct[col].dropna().astype(str)}
    else:
        category_map = distinct.set_index(col)["category"].astype(str).to_dict()

    order_baskets = (
        df.sort_values(["visit_id", "order_seq", "ordered_at", "line_index"])
        .groupby(["visit_id", "order_id"], sort=False)
        .agg(
            seq=("order_seq", "min"),
            ordered_at=("ordered_at", "min"),
            items=(col, lambda s: list(dict.fromkeys(map(str, s)))),
        )
        .reset_index()
        .sort_values(["visit_id", "seq", "ordered_at"])
    )

    for visit_id, group in order_baskets.groupby("visit_id", sort=False):
        item_lists = group["items"].tolist()
        for idx in range(len(item_lists) - 1):
            prev_items = item_lists[idx]
            next_items = item_lists[idx + 1]
            for item_a in prev_items:
                for item_b in next_items:
                    if item_a == item_b:
                        continue
                    pair = (item_a, item_b)
                    pair_count[pair] += 1
                    table_sets[pair].add(str(visit_id))
    return pair_count, table_sets, fd_map, category_map


def analysis_3_consecutive_pairs(df: pd.DataFrame, require_high_order: bool = False) -> dict:
    target = party2(df)
    if require_high_order:
        target = high_order_visits(target)
    pair_count, table_sets, fd_map, category_map = consecutive_pairs(target, "item")
    rows = []
    population_tables = max(1, target["visit_id"].nunique())
    for (item_a, item_b), count in pair_count.items():
        table_count = len(table_sets[(item_a, item_b)])
        if table_count < MIN_TABLES:
            continue
        rows.append({
            "item_a": item_a,
            "item_b": item_b,
            "pair": f"{item_a} → {item_b}",
            "pair_type": f"{fd_map.get(item_a)}→{fd_map.get(item_b)}",
            "category_pair": f"{category_map.get(item_a)}→{category_map.get(item_b)}",
            "sequence_count": int(count),
            "table_count": int(table_count),
            "support_pct": round(table_count / population_tables * 100, 2),
        })
    result = pd.DataFrame(rows)
    if not result.empty:
        result = result.sort_values(["table_count", "sequence_count"], ascending=False).head(10)
    return {
        "title": "3. 連続注文ペア TOP10",
        "population": {"visits": int(target["visit_id"].nunique()), "orders": int(target["order_id"].nunique())},
        "rows": result.to_dict("records") if not result.empty else [],
        "definition": "2名以上。隣接する別order_id間の有向ペア。全組合せ対象。10卓以上のみ。",
    }


def analysis_4_recommendation_candidates(df: pd.DataFrame) -> dict:
    target = high_order_visits(party2(df))
    pair_count, table_sets, fd_map, category_map = consecutive_pairs(target, "item")
    top_items = analysis_1_top_items(df)
    item_rank = {row["item_name"]: idx + 1 for idx, row in enumerate(top_items["overall"])}
    population_tables = max(1, target["visit_id"].nunique())

    rows = []
    for (item_a, item_b), count in pair_count.items():
        table_count = len(table_sets[(item_a, item_b)])
        if table_count < MIN_TABLES:
            continue
        rank_bonus = 0
        if item_a in item_rank:
            rank_bonus += max(0, 11 - item_rank[item_a])
        if item_b in item_rank:
            rank_bonus += max(0, 11 - item_rank[item_b])
        support = table_count / population_tables
        score = table_count * 2 + count * 0.5 + rank_bonus * 1.5 + support * 20
        rows.append({
            "pair": f"{item_a} → {item_b}",
            "item_a": item_a,
            "item_b": item_b,
            "pair_type": f"{fd_map.get(item_a)}→{fd_map.get(item_b)}",
            "category_pair": f"{category_map.get(item_a)}→{category_map.get(item_b)}",
            "sequence_count": int(count),
            "table_count": int(table_count),
            "support_pct": round(support * 100, 2),
            "top_item_bonus": round(rank_bonus, 2),
            "recommend_score": round(score, 2),
            "recommendation": f"「{item_a}」注文後に「{item_b}」を提案",
        })
    item_pairs = pd.DataFrame(rows)
    if not item_pairs.empty:
        item_pairs = item_pairs.sort_values(["recommend_score", "table_count"], ascending=False)

    def pick(kind: str) -> list[dict]:
        if item_pairs.empty:
            return []
        if kind == "food_food":
            mask = item_pairs["pair_type"] == "フード→フード"
        elif kind == "drink_drink":
            mask = item_pairs["pair_type"] == "ドリンク→ドリンク"
        else:
            mask = item_pairs["pair_type"].isin(["フード→ドリンク", "ドリンク→フード"])
        return item_pairs[mask].head(5).to_dict("records")

    category_count, category_tables, _, _ = consecutive_pairs(target, "category")
    cat_rows = []
    for (cat_a, cat_b), count in category_count.items():
        table_count = len(category_tables[(cat_a, cat_b)])
        if table_count < MIN_TABLES:
            continue
        support = table_count / population_tables
        cat_rows.append({
            "category_pair": f"{cat_a} → {cat_b}",
            "sequence_count": int(count),
            "table_count": int(table_count),
            "support_pct": round(support * 100, 2),
            "recommend_score": round(table_count * 2 + count * 0.5 + support * 20, 2),
        })
    category_pairs = pd.DataFrame(cat_rows)
    if not category_pairs.empty:
        category_pairs = category_pairs.sort_values(["recommend_score", "table_count"], ascending=False).head(5)

    return {
        "title": "4. 注文継続につながる商品組み合わせ 各Top5",
        "population": {"visits": int(target["visit_id"].nunique()), "orders": int(target["order_id"].nunique())},
        "food_food": pick("food_food"),
        "drink_drink": pick("drink_drink"),
        "food_drink": pick("food_drink"),
        "category_top5": category_pairs.to_dict("records") if not category_pairs.empty else [],
        "definition": "2名以上かつ15品以上の卓。同一母集団で、連続注文・高注文卓での頻出度・出現卓数をスコア化。",
    }


def run_all(df: pd.DataFrame) -> dict:
    return {
        "summary": summary(df),
        "analysis1": analysis_1_top_items(df),
        "analysis2": analysis_2_same_order_pairs(df),
        "analysis3": analysis_3_consecutive_pairs(df),
        "analysis4": analysis_4_recommendation_candidates(df),
    }
