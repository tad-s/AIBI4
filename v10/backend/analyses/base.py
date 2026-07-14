"""ベース分析 ①〜⑥（客単価・商品・顧客・滞在の分析）。"""
from __future__ import annotations

from collections import Counter
from itertools import combinations

import numpy as np
import pandas as pd

from analyses import charts

DOW = {0: "月", 1: "火", 2: "水", 3: "木", 4: "金", 5: "土", 6: "日"}


def _insufficient(aid: str, title: str, msg: str) -> dict:
    return {"id": aid, "title": title, "insight": msg, "insights": [], "advice": [],
            "chart": None, "table": None}


def _std_regression(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    xm, xs = X.mean(0), X.std(0)
    xs[xs == 0] = 1.0
    ym, ys = y.mean(), (y.std() or 1.0)
    Xs = (X - xm) / xs
    ys_arr = (y - ym) / ys
    A = np.column_stack([np.ones(len(Xs)), Xs])
    try:
        coef, *_ = np.linalg.lstsq(A, ys_arr, rcond=None)
        return coef[1:]
    except Exception:
        return np.zeros(X.shape[1])


# ── ① 客単価に影響する変数（標準化重回帰）──
def a1_variable_regression(odf: pd.DataFrame) -> dict:
    aid, title = "a1", "① 客単価に影響する変数"
    feats = [("時間帯", "時間帯"), ("曜日", "曜日"), ("商品数", "商品数"),
             ("人数", "人数"), ("滞在時間", "滞在時間"), ("ドリンク数", "ドリンク数")]
    names, cols = [], []
    for label, col in feats:
        if col in odf.columns:
            s = pd.to_numeric(odf[col], errors="coerce")
            if s.notna().sum() > 20 and s.nunique() > 1:
                names.append(label); cols.append(col)
    if len(cols) < 2 or len(odf) < 30:
        return _insufficient(aid, title, "重回帰に十分なデータがありません（30伝票以上必要）。")

    tmp = odf[cols + ["客単価"]].apply(pd.to_numeric, errors="coerce").dropna()
    if len(tmp) < 30:
        return _insufficient(aid, title, "重回帰に十分なデータがありません。")
    coef = _std_regression(tmp[cols].values.astype(float), tmp["客単価"].values.astype(float))
    order = np.argsort(np.abs(coef))[::-1]
    labels = [names[i] for i in order]
    vals = [round(float(coef[i]), 3) for i in order]
    colors = ["#e05a6d" if v > 0 else "#4f7bd8" for v in vals]
    # 横棒は上位を上に：反転
    opt = charts.bar_h(labels[::-1], [abs(v) for v in vals][::-1], colors=colors[::-1])
    top = labels[0]
    direction = "客単価を上げる" if vals[0] > 0 else "客単価を下げる"
    return {
        "id": aid, "title": title,
        "insight": f"**{top}** が客単価に最も強く影響（{direction}方向）。",
        "insights": [
            f"最も影響が大きい変数は **{top}**（{direction}方向）",
            "赤=正の影響（客単価UP）／青=負の影響（客単価DOWN）",
            f"正の影響: {', '.join([l for l, v in zip(labels, vals) if v > 0]) or 'なし'}",
        ],
        "advice": [
            f"{top} を意識した接客・導線設計で客単価を伸ばせる余地がある",
            "正の影響が大きい変数を増やす施策（追加提案・滞在価値向上）を優先",
        ],
        "chart": {"option": opt, "fmt": "float1", "height": 300},
        "table": {"columns": ["変数", "標準化係数"],
                  "rows": [[l, v] for l, v in zip(labels, vals)]},
    }


# ── ② 商品の客単価貢献（リフト）──
def a2_product_lift(odf: pd.DataFrame) -> dict:
    aid, title = "a2", "② 客単価を押し上げる商品"
    if "商品リスト" not in odf.columns or len(odf) < 20:
        return _insufficient(aid, title, "商品リストが不足しています。")
    overall = odf["客単価"].mean()
    freq = Counter(it for lst in odf["商品リスト"] for it in set(lst))
    common = [it for it, c in freq.items() if c >= max(5, len(odf) * 0.02)]
    if not common:
        return _insufficient(aid, title, "十分に出現する商品がありません。")
    lift = []
    for it in common:
        mask = odf["商品リスト"].apply(lambda lst: it in lst)
        avg_with = odf.loc[mask, "客単価"].mean()
        lift.append((it, avg_with - overall, int(mask.sum())))
    lift.sort(key=lambda x: x[1], reverse=True)
    top = lift[:10]
    labels = [t[0] for t in top][::-1]
    vals = [round(t[1]) for t in top][::-1]
    opt = charts.bar_h(labels, vals, color="#70ad47")
    return {
        "id": aid, "title": title,
        "insight": f"**{top[0][0]}** を含む伝票は平均より **{round(top[0][1]):,}円** 高い。",
        "insights": [
            f"客単価を最も押し上げる商品は **{top[0][0]}**（全体平均比 +{round(top[0][1]):,}円）",
            f"全体平均客単価: {round(overall):,}円",
            "これらの商品は「高単価伝票の起点」になっている可能性が高い",
        ],
        "advice": [
            f"**{top[0][0]}** をおすすめ・セットの核に据える",
            "上位商品を注文した客に相性の良い追加商品を提案し単価を伸ばす",
        ],
        "chart": {"option": opt, "fmt": "yen", "height": 320},
        "table": {"columns": ["商品", "平均比(円)", "出現伝票数"],
                  "rows": [[t[0], round(t[1]), t[2]] for t in top]},
    }


# ── ③ ABC分析（客単価グループ）──
def a3_abc(odf: pd.DataFrame) -> dict:
    aid, title = "a3", "③ ABC分析（客単価グループ）"
    if len(odf) < 30:
        return _insufficient(aid, title, "ABC分析に十分なデータがありません。")
    q33, q67 = odf["客単価"].quantile(0.33), odf["客単価"].quantile(0.67)
    grp = odf["客単価"].apply(lambda v: "高(A)" if v >= q67 else ("中(B)" if v >= q33 else "低(C)"))
    g = odf.groupby(grp)["客単価"].agg(["count", "mean"]).reindex(["高(A)", "中(B)", "低(C)"])
    avg_all = odf["客単価"].mean()
    labels = list(g.index)
    vals = [round(v) for v in g["mean"].tolist()]
    opt = charts.bar_v(labels, vals, colors=["#c0392b", "#e67e22", "#27ae60"])
    opt["series"][0]["markLine"] = {
        "silent": True, "data": [{"yAxis": round(avg_all)}],
        "lineStyle": {"color": "#f39c12", "type": "dashed"},
        "label": {"formatter": f"全体平均 {round(avg_all):,}円", "color": "#b8791a"},
    }
    a_avg, c_avg = g.loc["高(A)", "mean"], g.loc["低(C)", "mean"]
    return {
        "id": aid, "title": title,
        "insight": f"高(A) {round(a_avg):,}円 / 低(C) {round(c_avg):,}円（差 {round(a_avg - c_avg):,}円）。",
        "insights": [
            f"全体平均客単価: **{round(avg_all):,}円**",
            f"高(A)平均 {round(a_avg):,}円（{int(g.loc['高(A)','count'])}件） / 低(C)平均 {round(c_avg):,}円（{int(g.loc['低(C)','count'])}件）",
            f"A・C間の客単価差は **{round(a_avg - c_avg):,}円** — 上位客が売上を大きく左右",
        ],
        "advice": [
            "低(C)客への追加注文促進（サイド・デザート）で中間帯へ引き上げ",
            "高(A)客のリピート促進で売上の柱を維持",
        ],
        "chart": {"option": opt, "fmt": "yen", "height": 300},
        "table": {"columns": ["グループ", "件数", "平均客単価"],
                  "rows": [[i, int(g.loc[i, "count"]), round(g.loc[i, "mean"])] for i in labels]},
    }


# ── ④ バスケット分析（同時注文ペア）──
def a4_basket(odf: pd.DataFrame) -> dict:
    aid, title = "a4", "④ バスケット分析（同時注文ペア）"
    if "商品リスト" not in odf.columns or len(odf) < 20:
        return _insufficient(aid, title, "商品リストが不足しています。")
    pair = Counter()
    for lst in odf["商品リスト"]:
        uniq = list(dict.fromkeys([str(x) for x in lst if str(x) and str(x) != "nan"]))
        for a, b in combinations(uniq, 2):
            pair[tuple(sorted((a, b)))] += 1
    top = pair.most_common(10)
    if not top:
        return _insufficient(aid, title, "同時注文ペアが見つかりません。")
    labels = [f"{a} × {b}" for (a, b), _ in top][::-1]
    vals = [c for _, c in top][::-1]
    opt = charts.bar_h(labels, vals, color="#3b6ee8")
    (pa, pb), pc = top[0]
    return {
        "id": aid, "title": title,
        "insight": f"最も多い同時注文ペアは **{pa} × {pb}**（{pc}件）。",
        "insights": [
            f"同時注文が最も多いペア: **{pa} × {pb}**（{pc}件）",
            "上位ペアはセットメニュー・卓上POPの有力候補",
        ],
        "advice": [
            "上位ペアをセット商品化／レコメンド枠に反映",
            "ドリンク×フードのペアは特に追加提案が効きやすい",
        ],
        "chart": {"option": opt, "fmt": "int", "height": 320},
        "table": {"columns": ["組み合わせ", "件数"], "rows": [[f"{a} × {b}", c] for (a, b), c in top]},
    }


# ── ⑤ 曜日×時間帯 ヒートマップ ──
def a5_heatmap(odf: pd.DataFrame) -> dict:
    aid, title = "a5", "⑤ 曜日 × 時間帯 の来店ヒートマップ"
    if "時間帯" not in odf.columns or "曜日" not in odf.columns:
        return _insufficient(aid, title, "時間帯・曜日を算出できません。")
    d = odf.dropna(subset=["時間帯", "曜日"])
    if len(d) < 20:
        return _insufficient(aid, title, "十分なデータがありません。")
    hours = sorted(int(h) for h in d["時間帯"].unique())
    dows = list(range(7))
    ct = d.groupby(["曜日", "時間帯"]).size()
    cells, mx = [], 0
    for xi, h in enumerate(hours):
        for yi, dw in enumerate(dows):
            v = int(ct.get((dw, h), 0))
            mx = max(mx, v)
            cells.append([xi, yi, v])
    opt = charts.heatmap([f"{h}時" for h in hours], [DOW[d_] for d_ in dows], cells, mx)
    peak = ct.idxmax()
    return {
        "id": aid, "title": title,
        "insight": f"最も来店が集中するのは **{DOW[peak[0]]}曜 {int(peak[1])}時台**。",
        "insights": [
            f"来店ピークは **{DOW[peak[0]]}曜 {int(peak[1])}時台**（{int(ct.max())}件）",
            "曜日・時間帯で需要の濃淡がはっきり出ている",
        ],
        "advice": [
            "ピーク帯は回転率重視・人員厚め、閑散帯は追加注文で単価向上",
            "閑散帯限定の販促（タイムサービス）で需要を平準化",
        ],
        "chart": {"option": opt, "fmt": "int", "height": 300},
        "table": None,
    }


# ── ⑥ 滞在時間 × 客単価 ──
def a6_stay(odf: pd.DataFrame) -> dict:
    aid, title = "a6", "⑥ 滞在時間 × 客単価"
    if "滞在時間" not in odf.columns or odf["滞在時間"].notna().sum() < 20:
        return _insufficient(aid, title, "滞在時間を算出できるデータが不足しています。")
    d = odf.dropna(subset=["滞在時間"]).copy()
    bins = [0, 30, 60, 90, 120, 150, 9999]
    labels = ["0-30分", "30-60分", "60-90分", "90-120分", "120-150分", "150分超"]
    d["帯"] = pd.cut(d["滞在時間"], bins=bins, labels=labels)
    g = d.groupby("帯", observed=True)["客単価"].mean()
    lab = [str(x) for x in g.index]
    vals = [round(v) for v in g.tolist()]
    opt = charts.bar_v(lab, vals, color="#5b9bd5")
    corr = d["滞在時間"].corr(d["客単価"])
    return {
        "id": aid, "title": title,
        "insight": f"滞在時間と客単価の相関は **{corr:.2f}**。長時間客ほど単価が高い傾向。",
        "insights": [
            f"滞在時間と客単価の相関係数: **{corr:.2f}**",
            f"最高単価帯は **{lab[int(np.argmax(vals))]}**（{max(vals):,}円）",
        ],
        "advice": [
            "長時間滞在客には追加ドリンク・デザートの声かけで単価を伸ばす",
            "短時間客の多い時間帯は回転率、長時間客の時間帯は単価で最適化",
        ],
        "chart": {"option": opt, "fmt": "yen", "height": 300},
        "table": {"columns": ["滞在帯", "平均客単価"], "rows": [[l, v] for l, v in zip(lab, vals)]},
    }


def run_base(odf: pd.DataFrame) -> list[dict]:
    out = []
    for fn in [a1_variable_regression, a2_product_lift, a3_abc, a4_basket, a5_heatmap, a6_stay]:
        try:
            out.append(fn(odf))
        except Exception as e:
            out.append(_insufficient(fn.__name__, fn.__name__, f"計算エラー: {e}"))
    return out
