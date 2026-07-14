"""注文導線分析 ⑦〜⑫（注文の流れ・組み合わせ・連鎖・停止）。"""
from __future__ import annotations

from collections import Counter

import numpy as np
import pandas as pd

from analyses import charts
from analyses.base import _insufficient


def _seq_pairs(odf: pd.DataFrame) -> Counter:
    cnt = Counter()
    for lst in odf["商品リスト"]:
        items = [str(x) for x in lst if str(x) and str(x) != "nan"]
        for a, b in zip(items, items[1:]):
            if a != b:
                cnt[(a, b)] += 1
    return cnt


# ── ⑦ 注文の流れ ──
def a7_order_flow(odf: pd.DataFrame) -> dict:
    aid, title = "a7", "⑦ 注文の流れ"
    if "商品リスト" not in odf.columns or len(odf) < 10:
        return _insufficient(aid, title, "注文順序を分析できるデータが不足しています。")
    first_items = Counter(str(lst[0]) for lst in odf["商品リスト"] if lst)
    top_first = first_items.most_common(8)
    labels = [k for k, _ in top_first][::-1]
    vals = [v for _, v in top_first][::-1]
    opt = charts.bar_h(labels, vals, color="#5b9bd5")
    one_item_rate = float((odf["商品数"] == 1).mean() * 100)
    top_name = top_first[0][0] if top_first else "-"
    return {
        "id": aid, "title": title,
        "insight": f"初期注文の最多は **{top_name}**。1品のみで止まる伝票は **{one_item_rate:.1f}%**。",
        "insights": [
            f"初期注文（1品目）で最も多い商品は **{top_name}**",
            f"1品のみで止まる伝票比率は **{one_item_rate:.1f}%**",
            "初期注文はその後の追加提案の起点になる",
        ],
        "advice": [
            "初期注文直後に2品目候補を提示し1品止まりを減らす",
            f"**{top_name}** の近くに追加注文候補を配置する",
        ],
        "chart": {"option": opt, "fmt": "int", "height": 300},
        "table": {"columns": ["初期商品", "件数"], "rows": [[k, v] for k, v in top_first]},
    }


# ── ⑧ 売れるメニューの組み合わせ（連続注文）──
def a8_combinations(odf: pd.DataFrame) -> dict:
    aid, title = "a8", "⑧ 連続注文の組み合わせ（Aの後にB）"
    if "商品リスト" not in odf.columns or len(odf) < 10:
        return _insufficient(aid, title, "商品リストが不足しています。")
    seq = _seq_pairs(odf).most_common(10)
    if not seq:
        return _insufficient(aid, title, "連続注文のペアが見つかりません。")
    labels = [f"{a} → {b}" for (a, b), _ in seq][::-1]
    vals = [c for _, c in seq][::-1]
    opt = charts.bar_h(labels, vals, color="#e74c3c")
    (a, b), c = seq[0]
    return {
        "id": aid, "title": title,
        "insight": f"最も多い連続注文は **{a} → {b}**（{c}件）。追加提案の順序設計に使える。",
        "insights": [
            f"「{a}」の後に「{b}」が注文される流れが最多（{c}件）",
            "連続注文は追加提案（次の一手）の設計に直結する",
        ],
        "advice": [
            f"「{a}」注文後に「{b}」を次のおすすめとして提示",
            "連続ペアをモバイルオーダーの表示順・声かけに反映",
        ],
        "chart": {"option": opt, "fmt": "int", "height": 320},
        "table": {"columns": ["遷移", "件数"], "rows": [[f"{a} → {b}", c] for (a, b), c in seq]},
    }


# ── ⑨ 初期注文の影響 ──
def a9_initial_impact(odf: pd.DataFrame) -> dict:
    aid, title = "a9", "⑨ 初期注文の影響"
    if "商品リスト" not in odf.columns or len(odf) < 10:
        return _insufficient(aid, title, "初期注文を特定できません。")
    d = odf.copy()
    d["初期注文"] = d["商品リスト"].apply(lambda xs: str(xs[0]) if xs else "不明")
    g = d.groupby("初期注文").agg(件数=("客単価", "count"), 平均商品数=("商品数", "mean"),
                                    平均客単価=("客単価", "mean"))
    g = g[g["件数"] >= 3].sort_values("平均商品数", ascending=False).head(12)
    if g.empty:
        return _insufficient(aid, title, "十分な初期注文パターンがありません。")
    labels = list(g.index)[::-1]
    vals = [round(v, 1) for v in g["平均商品数"].tolist()][::-1]
    opt = charts.bar_h(labels, vals, color="#5b9bd5")
    top = g.index[0]
    return {
        "id": aid, "title": title,
        "insight": f"注文数を最も伸ばす初期注文は **{top}**（平均{g.iloc[0]['平均商品数']:.1f}品）。",
        "insights": [
            f"平均商品数が最大の初期注文は **{top}**（{g.iloc[0]['平均商品数']:.1f}品）",
            "初期注文はその後の注文点数に影響する",
        ],
        "advice": [
            f"**{top}** をファーストオーダー候補として提示",
            "初期1品だけの客には早めに相性商品を提案",
        ],
        "chart": {"option": opt, "fmt": "float1", "height": 320},
        "table": {"columns": ["初期注文", "件数", "平均商品数", "平均客単価"],
                  "rows": [[i, int(g.loc[i, "件数"]), round(g.loc[i, "平均商品数"], 1),
                            round(g.loc[i, "平均客単価"])] for i in g.index]},
    }


# ── ⑩ 注文の連鎖条件 ──
def a10_chain(odf: pd.DataFrame) -> dict:
    aid, title = "a10", "⑩ 注文の連鎖条件（品数帯分布）"
    if "商品数" not in odf.columns or len(odf) < 10:
        return _insufficient(aid, title, "商品数が不足しています。")
    d = odf.copy()
    bins = [0, 1, 2, 3, 5, 999]
    labels = ["1品", "2品", "3品", "4-5品", "6品以上"]
    d["品数帯"] = pd.cut(d["商品数"], bins=bins, labels=labels)
    g = d.groupby("品数帯", observed=True)["客単価"].agg(["count", "mean"])
    lab = [str(x) for x in g.index]
    vals = [int(v) for v in g["count"].tolist()]
    opt = charts.bar_v(lab, vals, color="#6c42f0")
    two_plus = float((d["商品数"] >= 2).mean() * 100)
    three_plus = float((d["商品数"] >= 3).mean() * 100)
    return {
        "id": aid, "title": title,
        "insight": f"2品以上に進む伝票は **{two_plus:.1f}%**、3品以上は **{three_plus:.1f}%**。",
        "insights": [
            f"2品以上に進む比率: **{two_plus:.1f}%**",
            f"3品以上に進む比率: **{three_plus:.1f}%**",
            "品数帯の山から注文連鎖の停滞点が読み取れる",
        ],
        "advice": [
            "1品止まりを減らす施策を最優先",
            "2品目注文後に3品目候補を提示して連鎖を促す",
        ],
        "chart": {"option": opt, "fmt": "int", "height": 300},
        "table": {"columns": ["品数帯", "件数", "平均客単価"],
                  "rows": [[l, int(g.loc[l, "count"]), round(g.loc[l, "mean"])] for l in lab]},
    }


# ── ⑪ 時間帯別の違い ──
def a11_timeband(odf: pd.DataFrame) -> dict:
    aid, title = "a11", "⑪ 時間帯別の違い（注文点数 × 客単価）"
    if "時間帯" not in odf.columns or odf["時間帯"].notna().sum() < 10:
        return _insufficient(aid, title, "時間帯を算出できません。")
    g = odf.dropna(subset=["時間帯"]).groupby("時間帯").agg(
        平均商品数=("商品数", "mean"), 平均客単価=("客単価", "mean")).sort_index()
    x = [f"{int(h)}時" for h in g.index]
    y1 = [round(v, 1) for v in g["平均商品数"].tolist()]
    y2 = [round(v) for v in g["平均客単価"].tolist()]
    opt = charts.dual_line(x, y1, "平均注文点数", y2, "平均客単価(円)")
    peak = g["平均商品数"].idxmax()
    return {
        "id": aid, "title": title,
        "insight": f"平均注文点数が最も高いのは **{int(peak)}時台**。",
        "insights": [
            f"注文点数が伸びる時間帯は **{int(peak)}時台**（{g.loc[peak, '平均商品数']:.1f}品）",
            "時間帯で注文点数と客単価の山が異なる",
        ],
        "advice": [
            "点数が伸びる時間帯に高単価商品の提案を強化",
            "軽い利用の時間帯は低負荷な追加商品を提示",
        ],
        "chart": {"option": opt, "fmt": "float1", "height": 300},
        "table": {"columns": ["時間帯", "平均商品数", "平均客単価"],
                  "rows": [[x[i], y1[i], y2[i]] for i in range(len(x))]},
    }


# ── ⑫ 注文が止まるポイント ──
def a12_stop(odf: pd.DataFrame) -> dict:
    aid, title = "a12", "⑫ 注文が止まるポイント"
    if "商品数" not in odf.columns or len(odf) < 10:
        return _insufficient(aid, title, "商品数が不足しています。")
    stop = odf["商品数"].clip(upper=8).value_counts().sort_index()
    lab = [f"{int(k)}品" for k in stop.index]
    vals = [int(v) for v in stop.tolist()]
    opt = charts.bar_v(lab, vals, color="#95a5a6")
    top_stop = int(stop.idxmax())
    last = Counter(str(lst[-1]) for lst in odf["商品リスト"] if lst).most_common(10)
    return {
        "id": aid, "title": title,
        "insight": f"注文が最も止まりやすいのは **{top_stop}品目**。",
        "insights": [
            f"最も多い停止ポイントは **{top_stop}品目**",
            f"最終注文で多い商品: {', '.join(k for k, _ in last[:3])}",
            "停止ポイント直前の提案が注文数増加の余地",
        ],
        "advice": [
            f"{top_stop}品目到達前に追加候補を提示",
            "最終注文で多い商品の後に締め・デザート・追加ドリンクを提案",
        ],
        "chart": {"option": opt, "fmt": "int", "height": 300},
        "table": {"columns": ["最終商品", "件数"], "rows": [[k, v] for k, v in last]},
    }


def run_order_flow(odf: pd.DataFrame) -> list[dict]:
    out = []
    for fn in [a7_order_flow, a8_combinations, a9_initial_impact, a10_chain, a11_timeband, a12_stop]:
        try:
            out.append(fn(odf))
        except Exception as e:
            out.append(_insufficient(fn.__name__, fn.__name__, f"計算エラー: {e}"))
    return out
