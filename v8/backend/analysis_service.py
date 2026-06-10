"""
analysis_service.py — 6項目の組み込み分析（V7.1 からの移植）
各関数は list[dict] を返す。各 dict は:
  { "title": str, "image_b64": str, "insight": str, "table": list[dict] | None }
"""
import io
import base64
from collections import Counter
from itertools import combinations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd

# ── 日本語フォント設定 ──
import platform
if platform.system() == "Windows":
    plt.rcParams["font.family"] = ["Yu Gothic", "Meiryo", "MS Gothic", "DejaVu Sans"]
else:
    plt.rcParams["font.family"] = ["Noto Sans CJK JP", "IPAGothic", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

# ── キーワード辞書 ──
_DRINK_KW = [
    "ビール","生ビール","生中","生大","ハイボール","チューハイ","酎ハイ",
    "サワー","レモンサワー","梅サワー","ワイン","日本酒","冷酒","熱燗",
    "焼酎","麦焼酎","芋焼酎","泡盛","ホッピー","カクテル","梅酒",
    "ウーロン茶","お茶","緑茶","麦茶","コーラ","ジュース",
    "ソフトドリンク","ノンアルコール","ノンアル","ドリンク","ソーダ",
]
_HEAVY_KW = [
    "唐揚げ","から揚げ","フライドチキン","揚げ","カツ","トンカツ",
    "天ぷら","フライ","コロッケ","串カツ","串揚げ",
    "焼き鳥","焼鳥","串焼き","焼肉","ステーキ","ハラミ","カルビ",
    "豚バラ","ロース","ネギ塩","つくね","もも",
    "鍋","おでん","煮込み","もつ煮",
    "ラーメン","うどん","そば","チャーハン","炒飯","焼きそば",
    "ご飯","おにぎり","餃子","ピザ","グラタン",
]
_LIGHT_KW = [
    "サラダ","野菜","枝豆","漬物","キムチ","冷奴","豆腐",
    "おひたし","和え物","小鉢","酢の物",
    "刺身","刺し身","お刺身","カルパッチョ","マリネ",
    "たこわさ","いかわさ",
    "アヒージョ","ナムル","ポテサラ","玉子","卵焼き","しらす",
]


def _kw_match(name, kw_list) -> bool:
    if pd.isna(name):
        return False
    return any(kw in str(name) for kw in kw_list)


def _fig_to_b64(fig, dpi=150) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
    buf.seek(0)
    plt.close(fig)
    return base64.b64encode(buf.read()).decode()


def _placeholder_b64(msg: str) -> str:
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.text(0.5, 0.5, msg, ha="center", va="center", fontsize=10, color="#666",
            bbox=dict(boxstyle="round,pad=0.6", facecolor="#f0f0f0", edgecolor="#ccc"))
    ax.axis("off")
    return _fig_to_b64(fig, dpi=90)


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


def build_order_df(df: pd.DataFrame) -> pd.DataFrame | None:
    """伝票単位の DataFrame を構築する。"""
    key_col = next((c for c in ["伝票番号", "注文番号"] if c in df.columns), None)
    amount_col = next((c for c in ["合計金額(税込)", "合計金額税込"] if c in df.columns), None)
    if key_col is None or amount_col is None:
        return None

    d = df.copy()
    d[amount_col] = pd.to_numeric(d[amount_col], errors="coerce")
    if "来店時間" in d.columns:
        d["来店時間"] = pd.to_datetime(d["来店時間"], errors="coerce")
    if "退店時間" in d.columns:
        d["退店時間"] = pd.to_datetime(d["退店時間"], errors="coerce")
    if "数量" in d.columns:
        d["数量"] = pd.to_numeric(d["数量"], errors="coerce")
    if "人数" in d.columns:
        d["人数"] = pd.to_numeric(d["人数"], errors="coerce")
    if "商品名" in d.columns:
        d["_is_drink"] = d["商品名"].apply(lambda x: _kw_match(x, _DRINK_KW)).astype(int)
        d["_is_heavy"] = d["商品名"].apply(lambda x: _kw_match(x, _HEAVY_KW)).astype(int)
        d["_is_light"] = d["商品名"].apply(lambda x: _kw_match(x, _LIGHT_KW)).astype(int)

    # receipt_no は同一店舗・同一日でも複数来店で重複するため来店時間との複合キーを使用
    if key_col == "伝票番号" and "来店時間" in d.columns:
        d["_basket_key"] = (
            d["来店時間"].dt.strftime("%Y%m%d%H%M%S").fillna("?")
            + "_" + d[key_col].astype(str)
        )
        groupby_col = "_basket_key"
    else:
        groupby_col = key_col

    agg: dict = {"客単価": (amount_col, "first")}
    for col, agg_key in [
        ("来店時間", ("来店時間", "first")),
        ("退店時間", ("退店時間", "first")),
        ("人数",     ("人数",     "first")),
        ("客層",     ("客層",     "first")),
        ("店舗名",   ("店舗名",   "first")),
    ]:
        if col in d.columns:
            agg[col] = agg_key
    if "商品名" in d.columns:
        agg["商品リスト"] = ("商品名", lambda x: list(x.dropna().astype(str)))
        agg["商品数"]    = ("商品名", "count")
    if "数量" in d.columns:
        agg["合計数量"] = ("数量", "sum")
    if "_is_drink" in d.columns:
        agg["ドリンク数"] = ("_is_drink", "sum")
        agg["ヘビー数"]   = ("_is_heavy", "sum")
        agg["ライト数"]   = ("_is_light", "sum")

    odf = d.groupby(groupby_col).agg(**agg).reset_index()
    odf.rename(columns={groupby_col: "注文ID"}, inplace=True)
    odf["客単価"] = pd.to_numeric(odf["客単価"], errors="coerce")
    odf = odf[odf["客単価"] > 0].dropna(subset=["客単価"])

    if "来店時間" in odf.columns:
        odf["曜日"]   = odf["来店時間"].dt.dayofweek
        odf["時間帯"] = odf["来店時間"].dt.hour
    if "来店時間" in odf.columns and "退店時間" in odf.columns:
        stay = (odf["退店時間"] - odf["来店時間"]).dt.total_seconds() / 60
        odf["滞在時間_分"] = stay.clip(0, 480)
    if "人数" in odf.columns:
        odf["人数"] = pd.to_numeric(odf["人数"], errors="coerce")
        valid_p = odf["人数"] > 0
        odf.loc[valid_p, "一人単価"] = (
            odf.loc[valid_p, "客単価"] / odf.loc[valid_p, "人数"]
        )
    if "ドリンク数" in odf.columns and "商品数" in odf.columns:
        odf["FD比率"] = (odf["ドリンク数"] / odf["商品数"].replace(0, 1)).clip(0, 1)

    return odf


# ── 分析① 客単価に影響を与える変数（重回帰）──
def analysis_1_variable_regression(order_df: pd.DataFrame | None) -> list[dict]:
    results = []
    use_dummy = True

    if order_df is not None and len(order_df) >= 30:
        feature_names, X_list = [], []
        for fname, col in [
            ("注文時間帯","時間帯"),("曜日","曜日"),("FD比率","FD比率"),
            ("商品数","商品数"),("人数","人数"),("滞在時間_分","滞在時間_分"),
            ("ドリンク数","ドリンク数"),
        ]:
            if col in order_df.columns:
                s = pd.to_numeric(order_df[col], errors="coerce")
                if s.notna().sum() > 20:
                    feature_names.append(fname)
                    X_list.append(s.values)
        if len(X_list) >= 2:
            tmp = pd.DataFrame(dict(zip(feature_names, X_list)), index=order_df.index)
            tmp["客単価"] = order_df["客単価"].values
            tmp = tmp.dropna()
            if len(tmp) >= 30:
                X = tmp[feature_names].values.astype(float)
                y = tmp["客単価"].values.astype(float)
                coef = _std_regression(X, y)
                idx = np.argsort(np.abs(coef))[::-1]
                names = [feature_names[i] for i in idx]
                vals  = coef[idx]
                colors = ["#e74c3c" if c > 0 else "#3498db" for c in vals]

                fig, ax = plt.subplots(figsize=(8, 4))
                ax.bar(names, np.abs(vals), color=colors, edgecolor="white")
                ax.set_ylabel("影響度合い（β係数の絶対値）")
                ax.set_title("客単価への影響度（重回帰分析）")
                ax.legend(handles=[
                    mpatches.Patch(color="#e74c3c", label="正の影響（客単価UP方向）"),
                    mpatches.Patch(color="#3498db", label="負の影響（客単価DOWN方向）"),
                ], fontsize=8)
                plt.xticks(rotation=30, ha="right")
                plt.tight_layout()

                top = names[0]
                dir0 = "客単価UP方向" if vals[0] > 0 else "客単価DOWN方向"
                up_vars = [n for n, c in zip(names, vals) if c > 0]
                dn_vars = [n for n, c in zip(names, vals) if c < 0]
                insights_list = [f"**{top}** が客単価に最も強く影響（{dir0}）"]
                if len(names) >= 2:
                    dir1 = "UP方向" if vals[1] > 0 else "DOWN方向"
                    insights_list.append(f"2位: **{names[1]}**（{dir1}）")
                if up_vars:
                    insights_list.append(f"客単価を上げる傾向の変数: {', '.join(up_vars[:3])}")
                if dn_vars:
                    insights_list.append(f"客単価を下げる傾向の変数: {', '.join(dn_vars[:3])}")
                advice_list = []
                if "FD比率" in up_vars:
                    advice_list.append("FD比率向上のためドリンク注文を促すオペレーションが有効")
                if "滞在時間_分" in up_vars:
                    advice_list.append("長時間滞在を促すイベントや居心地改善が売上向上につながる")
                if "人数" in up_vars:
                    advice_list.append("グループ来店促進（宴会パック、グループ割引）が有効")
                if "商品数" in up_vars:
                    advice_list.append("追加注文を促す卓上POPやスタッフ声がけが効果的")
                if "注文時間帯" in names[:3]:
                    advice_list.append("時間帯別メニューや限定商品で高単価帯の来客を増やす施策を検討")
                if not advice_list:
                    advice_list.append(f"影響度1位の **{top}** を起点に、客単価向上施策の優先順位を設定する")
                results.append({
                    "title": "分析① 客単価への影響度（重回帰分析）",
                    "image_b64": _fig_to_b64(fig),
                    "insight": f"**{top}** が客単価に最も影響しています（{dir0}）。",
                    "insights": insights_list,
                    "advice": advice_list,
                    "table": [{"変数名": n, "β係数": round(float(v), 3)} for n, v in zip(names, vals)],
                })
                use_dummy = False

    if use_dummy:
        feat_d = ["注文商品","FD比率","注文時間帯","客層","1組あたり客数","曜日・時間帯","その他"]
        val_d  = [0.85, 0.72, 0.58, 0.31, 0.28, 0.12, 0.09]
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.bar(feat_d, val_d, color="#5b9bd5", edgecolor="white")
        ax.set_ylabel("影響度合い（β係数の絶対値）")
        ax.set_title("客単価への影響度（重回帰分析）※ダミーデータ")
        plt.xticks(rotation=30, ha="right")
        plt.tight_layout()
        results.append({
            "title": "分析① 客単価への影響度（重回帰分析）※ダミーデータ",
            "image_b64": _fig_to_b64(fig),
            "insight": "ダミー例：「注文商品」「FD比率」「注文時間帯」が客単価に大きく影響。",
            "insights": ["注文商品・FD比率・注文時間帯が客単価に大きく影響（ダミー例）"],
            "advice": ["ドリンク注文の促進（FD比率向上）や時間帯別施策が客単価UPに有効と想定"],
            "table": None,
        })
    return results


# ── 分析② 商品別 客単価への影響度（重回帰）──
def analysis_2_product_regression(order_df: pd.DataFrame | None) -> list[dict]:
    results = []
    use_dummy = True

    if order_df is not None and "商品リスト" in order_df.columns and len(order_df) >= 30:
        try:
            all_items = [it for lst in order_df["商品リスト"] for it in lst if it and it != "nan"]
            exclude = ["レジ袋","袋","クーポン","割引","引","0円"]
            top_items = [
                it for it, _ in Counter(all_items).most_common(40)
                if not any(ex in it for ex in exclude)
            ][:15]

            if len(top_items) >= 5:
                rows = []
                for _, row in order_df.iterrows():
                    item_set = set(row["商品リスト"])
                    enc = {it: int(it in item_set) for it in top_items}
                    enc["客単価"] = row["客単価"]
                    rows.append(enc)
                hot = pd.DataFrame(rows).dropna()
                if len(hot) >= 30:
                    coef = _std_regression(hot[top_items].values.astype(float),
                                           hot["客単価"].values.astype(float))
                    sort_idx = np.argsort(coef)[::-1]
                    top5p = [i for i in sort_idx if coef[i] > 0][:5]
                    top5n = [i for i in reversed(sort_idx) if coef[i] < 0][:5]
                    show_idx = top5p + top5n
                    show_names = [top_items[i] for i in show_idx]
                    show_coef  = [coef[i] for i in show_idx]
                    colors = ["#e74c3c" if c > 0 else "#3498db" for c in show_coef]

                    fig, ax = plt.subplots(figsize=(9, 4))
                    ax.bar(show_names, show_coef, color=colors, edgecolor="white")
                    ax.axhline(0, color="black", linewidth=0.8, linestyle="--")
                    ax.set_ylabel("標準化係数（β係数）")
                    ax.set_title("商品別 客単価への影響度（重回帰分析）")
                    ax.legend(handles=[
                        mpatches.Patch(color="#e74c3c", label="客単価UP方向"),
                        mpatches.Patch(color="#3498db", label="客単価DOWN方向"),
                    ], fontsize=8)
                    plt.xticks(rotation=35, ha="right", fontsize=8)
                    plt.tight_layout()

                    pos_items = [show_names[i] for i, c in enumerate(show_coef) if c > 0]
                    neg_items = [show_names[i] for i, c in enumerate(show_coef) if c < 0]
                    insights_list2, advice_list2 = [], []
                    if pos_items:
                        insights_list2.append(f"**客単価UP商品**: {', '.join(pos_items[:3])} — これらを注文した客ほど伝票単価が高い傾向")
                        advice_list2.append(f"「{pos_items[0]}」などUP商品をおすすめ欄・卓上POPで前面に出し、追加注文を促す")
                    if neg_items:
                        insights_list2.append(f"**客単価DOWN商品**: {', '.join(neg_items[:3])} — 炭水化物系など「締め」商品は満腹感で他注文を減らす傾向")
                        advice_list2.append(f"「{neg_items[0]}」などDOWN商品は単体推奨より、UP商品とのセット提案で客単価を維持する")
                    if not insights_list2:
                        insights_list2 = ["分析結果から有意な傾向が確認されました"]
                    if not advice_list2:
                        advice_list2 = ["UP商品の推奨強化と、DOWN商品のセット販売を組み合わせた施策を検討"]
                    insight_str = ""
                    if pos_items:
                        insight_str += f"客単価UP商品: {', '.join(pos_items[:3])}。"
                    if neg_items:
                        insight_str += f" 客単価DOWN商品: {', '.join(neg_items[:3])}。"
                    results.append({
                        "title": "分析② 商品別 客単価への影響度（重回帰分析）",
                        "image_b64": _fig_to_b64(fig),
                        "insight": insight_str.strip(),
                        "insights": insights_list2,
                        "advice": advice_list2,
                        "table": [{"商品名": n, "β係数": round(float(c), 3)}
                                  for n, c in zip(show_names, show_coef)],
                    })
                    use_dummy = False
        except Exception:
            pass

    if use_dummy:
        items_d = ["もつ煮込み","本日のなめろう","牛たんタタキ","かんぱち刺し","やきとん","牛たん焼きそば"]
        coef_d  = [0.78, 0.65, 0.52, 0.18, 0.10, -0.42]
        colors_d = ["#e74c3c" if c > 0 else "#3498db" for c in coef_d]
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.bar(items_d, coef_d, color=colors_d, edgecolor="white")
        ax.axhline(0, color="black", linewidth=0.8, linestyle="--")
        ax.set_ylabel("標準化係数（β係数）")
        ax.set_title("商品別 客単価への影響度（重回帰分析）※ダミーデータ")
        plt.xticks(rotation=30, ha="right")
        plt.tight_layout()
        results.append({
            "title": "分析② 商品別 客単価への影響度（重回帰分析）※ダミーデータ",
            "image_b64": _fig_to_b64(fig),
            "insight": "ダミー例：「もつ煮込み」「なめろう」「牛たんタタキ」は客単価UPに寄与。",
            "insights": [
                "客単価UP商品（ダミー例）: もつ煮込み、なめろう、牛たんタタキ — 高単価客ほど頼む傾向",
                "客単価DOWN商品（ダミー例）: 牛たん焼きそば — 炭水化物系は満腹感で他注文を減らす傾向",
            ],
            "advice": [
                "UP商品をおすすめメニュー欄・卓上POPで強調し、注文率を上げる",
                "DOWN商品（炭水化物系）はコース終盤に位置づけ、早期注文を避ける声がけが有効",
            ],
            "table": None,
        })
    return results


# ── 分析③ ABC分析 ──
def analysis_3_abc_analysis(order_df: pd.DataFrame | None) -> list[dict]:
    results = []
    use_dummy = True

    if order_df is not None and len(order_df) >= 30 and "商品リスト" in order_df.columns:
        try:
            odf = order_df.copy()
            q33 = odf["客単価"].quantile(0.33)
            q67 = odf["客単価"].quantile(0.67)
            odf["客単価グループ"] = odf["客単価"].apply(
                lambda v: "高（A）" if v >= q67 else ("中（B）" if v >= q33 else "低（C）")
            )
            gs = odf.groupby("客単価グループ").agg(
                件数=("客単価","count"), 平均客単価=("客単価","mean")
            ).reindex(["高（A）","中（B）","低（C）"])
            avg_all = odf["客単価"].mean()

            fig1, ax1 = plt.subplots(figsize=(5, 3.5))
            ax1.bar(gs.index, gs["平均客単価"], color=["#c0392b","#e67e22","#27ae60"], edgecolor="white")
            ax1.axhline(avg_all, color="orange", linewidth=2, linestyle="--", label=f"全体平均 {avg_all:,.0f}円")
            ax1.set_ylabel("平均客単価（円）")
            ax1.set_title("ABC分析 - グループ別 平均客単価")
            ax1.legend(fontsize=8)
            plt.tight_layout()
            a_avg = gs.loc["高（A）", "平均客単価"]
            c_avg = gs.loc["低（C）", "平均客単価"]
            gap = a_avg - c_avg
            a_cnt = int(gs.loc["高（A）", "件数"])
            c_cnt = int(gs.loc["低（C）", "件数"])
            results.append({
                "title": "分析③ ABC分析 - グループ別 平均客単価",
                "image_b64": _fig_to_b64(fig1),
                "insight": (f"全体平均 {avg_all:,.0f}円 | "
                            f"高（A）: {a_avg:,.0f}円 / 低（C）: {c_avg:,.0f}円"),
                "insights": [
                    f"全体平均客単価: **{avg_all:,.0f}円**",
                    f"高単価グループ（A）平均: {a_avg:,.0f}円（{a_cnt}件） / 低単価グループ（C）平均: {c_avg:,.0f}円（{c_cnt}件）",
                    f"A・C間の客単価差は **{gap:,.0f}円** — 上位客の購買行動が売上を大きく左右している",
                ],
                "advice": [
                    f"低単価グループ（C）客に追加注文を促す施策（{c_avg:,.0f}円 → 中間帯への引き上げ）が全体売上向上に直結",
                    "Cグループに人気のサイドメニューやデザートを低価格帯で提案し、購入点数を増やす",
                    "Aグループのリピート来店を促進（ポイントカード、優待案内）し高単価客の離脱を防ぐ",
                ],
                "table": gs.reset_index().to_dict("records"),
            })

            # ─── 客層別 来客数・客単価分析 ───
            if "客層" in odf.columns and odf["客層"].notna().sum() >= 10:
                layer_grp = odf.groupby("客層").agg(
                    件数=("客単価","count"),
                    平均客単価=("客単価","mean"),
                ).sort_values("平均客単価", ascending=False)

                if len(layer_grp) >= 2:
                    fig2, ax_l1 = plt.subplots(figsize=(8, 4))
                    ax_l2 = ax_l1.twinx()
                    layer_colors = {"VIP":"#c0392b","会員":"#e67e22","リピーター":"#27ae60","新規":"#5b9bd5"}
                    bar_colors = [layer_colors.get(l, "#95a5a6") for l in layer_grp.index]
                    bars = ax_l1.bar(layer_grp.index, layer_grp["件数"],
                                     color=bar_colors, alpha=0.75, label="来客数")
                    ax_l2.plot(layer_grp.index, layer_grp["平均客単価"],
                               marker="o", color="#2c3e50", linewidth=2.5, label="平均客単価", zorder=5)
                    for bar in bars:
                        h = bar.get_height()
                        ax_l1.text(bar.get_x() + bar.get_width()/2,
                                   h + layer_grp["件数"].max()*0.01,
                                   f"{int(h)}件", ha="center", va="bottom", fontsize=8)
                    for xi, (lbl, row) in enumerate(layer_grp.iterrows()):
                        ax_l2.text(xi, row["平均客単価"] + layer_grp["平均客単価"].max()*0.02,
                                   f"{row['平均客単価']:,.0f}円", ha="center", va="bottom", fontsize=8)
                    ax_l1.set_ylabel("来客数（件）")
                    ax_l2.set_ylabel("平均客単価（円）")
                    ax_l1.set_title("客層別 来客数 × 平均客単価")
                    h1, lb1 = ax_l1.get_legend_handles_labels()
                    h2, lb2 = ax_l2.get_legend_handles_labels()
                    ax_l1.legend(h1+h2, lb1+lb2, loc="upper right", fontsize=8)
                    plt.tight_layout()

                    top_layer    = layer_grp.index[0]
                    bottom_layer = layer_grp.index[-1]
                    top_cnt_layer = layer_grp["件数"].idxmax()
                    results.append({
                        "title": "分析③ 客層別 来客数 × 平均客単価",
                        "image_b64": _fig_to_b64(fig2),
                        "insight": (f"平均客単価 最高: **{top_layer}**（{layer_grp.loc[top_layer,'平均客単価']:,.0f}円）"
                                    f" / 来客数 最多: **{top_cnt_layer}**"),
                        "insights": [
                            f"平均客単価 最高の客層: **{top_layer}**（{layer_grp.loc[top_layer,'平均客単価']:,.0f}円）",
                            f"来客数 最多の客層: **{top_cnt_layer}**（{int(layer_grp.loc[top_cnt_layer,'件数'])}件）",
                            f"平均客単価 最低の客層: **{bottom_layer}**（{layer_grp.loc[bottom_layer,'平均客単価']:,.0f}円）— リピーター転換・単価向上の優先対象",
                        ],
                        "advice": [
                            f"**{bottom_layer}** 層へのリピーター育成施策（スタンプカード・次回来店クーポン）で来店頻度と客単価を引き上げる",
                            f"**{top_layer}** 層向けに高付加価値メニュー・優待プログラムを設計し、離脱を防いで売上の柱を守る",
                            "客層ごとに推奨トークを標準化し、全スタッフが同じアップセル策を実行できる体制を整える",
                        ],
                        "table": layer_grp.reset_index().to_dict("records"),
                    })
            use_dummy = False
        except Exception:
            pass

    if use_dummy:
        grps = ["高（A）","中（B）","低（C）"]
        avgs = [7200, 4500, 2100]
        fig_d, ax_d = plt.subplots(figsize=(5, 3.5))
        ax_d.bar(grps, avgs, color=["#c0392b","#e67e22","#27ae60"], edgecolor="white")
        ax_d.axhline(3000, color="orange", linewidth=2, linestyle="--", label="平均 3,000円")
        ax_d.set_ylabel("平均客単価（円）")
        ax_d.set_title("ABC分析 - グループ別 平均客単価 ※ダミーデータ")
        ax_d.legend(fontsize=8)
        plt.tight_layout()
        results.append({
            "title": "分析③ ABC分析 ※ダミーデータ",
            "image_b64": _fig_to_b64(fig_d),
            "insight": "ダミー例：高（A）グループの平均客単価は低（C）の約3.4倍。",
            "insights": [
                "高（A）グループの平均客単価は低（C）の約3.4倍（ダミー例）",
                "上位客の購買行動が全体売上を大きく左右している",
            ],
            "advice": [
                "低単価（C）グループへの追加注文促進で全体売上が向上",
                "高単価（A）グループのリピート来店を促進（ポイントカード、優待案内）",
            ],
            "table": None,
        })
    return results


# ── 分析④ バスケット分析 ──
_DRINK_KEYWORDS_4 = [
    "コーヒー","ラテ","エスプレッソ","カプチーノ","ティー","紅茶","緑茶",
    "ジュース","スムージー","フラペ","アメリカーノ","マキアート","モカ",
    "カフェオレ","ソーダ","レモネード","ミルク","ホットチョコ","ドリンク",
    "ビール","サワー","ハイボール","日本酒","ワイン","チューハイ",
    "ウーロン","ウイスキー","焼酎","梅酒","酎ハイ","ソフトドリンク",
    "烏龍","コーラ","ジンジャー",
]

def _item_category_4(name: str) -> str:
    return "ドリンク" if any(kw in name for kw in _DRINK_KEYWORDS_4) else "フード"


def analysis_4_basket(order_df: pd.DataFrame | None) -> list[dict]:
    results = []
    use_dummy = True

    if order_df is not None and "商品リスト" in order_df.columns and len(order_df) >= 20:
        try:
            exclude = ["レジ袋","袋","クーポン","割引","引","0円"]
            clean_orders = [
                [it for it in lst if it and not any(ex in it for ex in exclude)]
                for lst in order_df["商品リスト"]
            ]
            clean_orders = [lst for lst in clean_orders if len(lst) >= 2]

            if len(clean_orders) >= 10:
                all_items = [it for lst in clean_orders for it in lst]
                top_items = [it for it, _ in Counter(all_items).most_common(12)]
                pair_count: Counter = Counter()
                for lst in clean_orders:
                    filtered = [it for it in lst if it in top_items]
                    for a, b in combinations(set(filtered), 2):
                        pair_count[tuple(sorted([a, b]))] += 1

                # ─── ① 全体の共起傾向 ───
                n = len(top_items)
                mat = np.zeros((n, n))
                item_idx = {it: i for i, it in enumerate(top_items)}
                for (a, b), cnt in pair_count.items():
                    if a in item_idx and b in item_idx:
                        i, j = item_idx[a], item_idx[b]
                        mat[i, j] = cnt
                        mat[j, i] = cnt

                fig1, ax1 = plt.subplots(figsize=(7, 6))
                im = ax1.imshow(mat, cmap="YlOrRd", aspect="auto")
                ax1.set_xticks(range(n))
                ax1.set_yticks(range(n))
                short = [it[:10] for it in top_items]
                ax1.set_xticklabels(short, rotation=45, ha="right", fontsize=7)
                ax1.set_yticklabels(short, fontsize=7)
                plt.colorbar(im, ax=ax1, shrink=0.8)
                ax1.set_title("商品共起頻度ヒートマップ（全体）")
                plt.tight_layout()

                top_pairs = pair_count.most_common(10)
                pair_table = [{"商品ペア": f"{a} × {b}", "共起件数": cnt}
                               for (a, b), cnt in top_pairs]

                results.append({
                    "title": "分析④ バスケット① 全体の共起傾向",
                    "image_b64": _fig_to_b64(fig1),
                    "insight": (
                        "グループ注文ではテーブル全員がそれぞれドリンクを注文するため、"
                        "ドリンク同士の組み合わせが上位に入りやすい傾向があります。"
                    ),
                    "insights": [
                        "グループ注文ではテーブル全員がそれぞれドリンクを注文するため、ドリンク同士の組み合わせが上位に入りやすい",
                        "テーブル単位の注文構造と人気商品の共起パターンが可視化されている",
                    ],
                    "advice": [
                        "共起頻度の高いペアをセットメニューに組み込み、注文の流れをデザインする",
                        "ヒートマップで濃い組み合わせはスタッフの推奨トークに活用する",
                    ],
                    "table": pair_table,
                })

                # ─── ② ドリンク×フード クロスカテゴリ ───
                cross_counter = Counter({
                    pair: cnt for pair, cnt in pair_count.items()
                    if _item_category_4(pair[0]) != _item_category_4(pair[1])
                })
                top_cross = cross_counter.most_common(10)
                if top_cross:
                    labels = [f"{a} × {b}" for (a, b), _ in top_cross]
                    vals   = [cnt for _, cnt in top_cross]
                    fig2, ax2 = plt.subplots(figsize=(7, max(4, len(labels) * 0.45)))
                    bars = ax2.barh(labels[::-1], vals[::-1], color="#5b9bd5", edgecolor="white")
                    for bar, v in zip(bars, vals[::-1]):
                        ax2.text(bar.get_width() + max(vals) * 0.01,
                                 bar.get_y() + bar.get_height() / 2,
                                 f"{v}件", va="center", fontsize=8)
                    ax2.set_xlabel("共起件数")
                    ax2.set_title("ドリンク × フード クロスカテゴリ Top10")
                    ax2.set_xlim(0, max(vals) * 1.2)
                    plt.tight_layout()

                    best = top_cross[0]
                    top3_cross = [f"{a} × {b}" for (a, b), _ in top_cross[:3]]
                    cross_table = [{"商品ペア": f"{a} × {b}", "共起件数": cnt}
                                   for (a, b), cnt in top_cross]
                    results.append({
                        "title": "分析④ バスケット② ドリンク×フード クロスカテゴリ",
                        "image_b64": _fig_to_b64(fig2),
                        "insight": (
                            f"クロスカテゴリ No.1: **{best[0][0]}** × **{best[0][1]}**（{best[1]}件）"
                        ),
                        "insights": [
                            f"クロスカテゴリ No.1: **{best[0][0]}** × **{best[0][1]}**（{best[1]}件）",
                            f"上位3ペア: {', '.join(top3_cross)} — これらがセット注文の核心",
                            "ドリンク×フードの組み合わせは、テーブル全体の注文量拡大に直結するシグナル",
                        ],
                        "advice": [
                            f"「{best[0][0]}」×「{best[0][1]}」をセットメニュー化し、単品より割安感を演出する",
                            "上位クロスペアを卓上POPや口頭推奨に活用し、追加注文率を高める",
                            "フードを注文した客にドリンクを勧めるスクリプトをスタッフに共有",
                        ],
                        "table": cross_table,
                    })

                use_dummy = False
        except Exception:
            pass

    if use_dummy:
        items_d = ["バーガー","ポテト","ドリンク","ナゲット","サラダ","アップル","コーヒー","チキン"]
        n_d = len(items_d)
        mat_d = np.array([
            [0,85,90,40,20,15,30,35],[85,0,78,55,18,12,20,40],
            [90,78,0,38,25,20,60,33],[40,55,38,0,10,8,15,28],
            [20,18,25,10,0,30,22,12],[15,12,20,8,30,0,18,9],
            [30,20,60,15,22,18,0,14],[35,40,33,28,12,9,14,0],
        ], dtype=float)
        fig_d, ax_d = plt.subplots(figsize=(6, 5))
        im_d = ax_d.imshow(mat_d, cmap="YlOrRd", aspect="auto")
        ax_d.set_xticks(range(n_d))
        ax_d.set_yticks(range(n_d))
        ax_d.set_xticklabels(items_d, rotation=45, ha="right", fontsize=8)
        ax_d.set_yticklabels(items_d, fontsize=8)
        plt.colorbar(im_d, ax=ax_d, shrink=0.8)
        ax_d.set_title("商品共起頻度ヒートマップ ※ダミーデータ")
        plt.tight_layout()
        results.append({
            "title": "分析④ バスケット分析 ※ダミーデータ",
            "image_b64": _fig_to_b64(fig_d),
            "insight": "ダミー例：バーガー×ドリンク・バーガー×ポテトの組み合わせが最も多い。",
            "insights": [
                "バーガー×ドリンク・バーガー×ポテトの組み合わせが最も頻出（ダミー例）",
                "グループ注文ではドリンク同士の共起が多く出やすい構造がある",
            ],
            "advice": [
                "共起頻度の高いペアをセットメニューに組み込み、注文単価を引き上げる",
                "ドリンク×フードの相互推奨を卓上POPやスタッフトークに活用する",
            ],
            "table": [{"商品ペア":"バーガー × ドリンク","共起件数":90},
                      {"商品ペア":"バーガー × ポテト","共起件数":85}],
        })
    return results


# ── 分析⑤ 曜日×時間帯 売上ヒートマップ ──
def analysis_5_dayhour_heatmap(order_df: pd.DataFrame | None) -> list[dict]:
    results = []
    use_dummy = True
    _DAY_LABELS = {0:"月", 1:"火", 2:"水", 3:"木", 4:"金", 5:"土", 6:"日"}

    if (order_df is not None and "曜日" in order_df.columns
            and "時間帯" in order_df.columns and len(order_df) >= 30):
        try:
            odf = order_df.copy()

            # ─── Chart 1: 来客数ヒートマップ（曜日×時間帯）───
            pivot_cnt = (
                odf.groupby(["曜日","時間帯"]).size()
                .unstack(fill_value=0)
            )

            if pivot_cnt.shape[1] >= 3:
                fig1, ax1 = plt.subplots(figsize=(11, 3.5))
                im = ax1.imshow(pivot_cnt.values, cmap="YlOrRd", aspect="auto")
                ax1.set_yticks(range(len(pivot_cnt.index)))
                ax1.set_yticklabels([_DAY_LABELS.get(i, str(i)) for i in pivot_cnt.index], fontsize=9)
                ax1.set_xticks(range(len(pivot_cnt.columns)))
                ax1.set_xticklabels([f"{h}時" for h in pivot_cnt.columns],
                                     rotation=45, ha="right", fontsize=8)
                plt.colorbar(im, ax=ax1, label="来客数", shrink=0.8)
                ax1.set_title("曜日 × 時間帯別 来客数ヒートマップ")
                plt.tight_layout()

                flat = pivot_cnt.values
                peak_r, peak_c = np.unravel_index(flat.argmax(), flat.shape)
                peak_day_lbl  = _DAY_LABELS.get(pivot_cnt.index[peak_r], "?")
                peak_hour     = pivot_cnt.columns[peak_c]
                day_total     = pivot_cnt.sum(axis=1)
                best_day      = _DAY_LABELS.get(int(day_total.idxmax()), "?")
                worst_day     = _DAY_LABELS.get(int(day_total.idxmin()), "?")
                hour_total    = pivot_cnt.sum(axis=0)
                low_hours     = [str(h) for h in hour_total.nsmallest(2).index.tolist()]

                results.append({
                    "title": "分析⑤ 曜日×時間帯 来客数ヒートマップ",
                    "image_b64": _fig_to_b64(fig1),
                    "insight": f"最繁忙帯: **{peak_day_lbl}曜日 {peak_hour}時台**",
                    "insights": [
                        f"最繁忙帯: **{peak_day_lbl}曜日 {peak_hour}時台** — ここに人員・仕込みを集中する",
                        f"来客数 最多の曜日: **{best_day}曜日** / 最少の曜日: **{worst_day}曜日**",
                        f"閑散時間帯（{', '.join([h+'時台' for h in low_hours])}）はタイムセール・SNS集客の好機",
                    ],
                    "advice": [
                        f"繁忙帯（{peak_day_lbl}曜日 {peak_hour}時前後）にシフトを集中し、提供スピードと客席回転率を最大化",
                        f"閑散帯（{', '.join([h+'時台' for h in low_hours])}）限定の割引・セット販売で来客を誘引する",
                        f"{worst_day}曜日は特別イベント・SNSキャンペーンを集中投下して底上げを狙う",
                    ],
                    "table": None,
                })

            # ─── Chart 2: 曜日別 来客数 × 平均客単価（棒＋折れ線）───
            day_grp = (
                odf.groupby("曜日").agg(
                    来客数=("客単価","count"),
                    平均客単価=("客単価","mean"),
                )
                .reindex(range(7), fill_value=0)
            )
            day_grp.index = [_DAY_LABELS.get(i, str(i)) for i in day_grp.index]
            day_grp = day_grp[day_grp["来客数"] > 0]

            if len(day_grp) >= 2:
                fig2, ax_d1 = plt.subplots(figsize=(8, 4))
                ax_d2 = ax_d1.twinx()
                ax_d1.bar(day_grp.index, day_grp["来客数"],
                          color="#5b9bd5", alpha=0.75, label="来客数")
                ax_d2.plot(day_grp.index, day_grp["平均客単価"],
                           marker="o", color="#e74c3c", linewidth=2.5, label="平均客単価", zorder=5)
                ax_d1.set_ylabel("来客数（件）", color="#5b9bd5")
                ax_d2.set_ylabel("平均客単価（円）", color="#e74c3c")
                ax_d1.set_title("曜日別 来客数 × 平均客単価")
                h1, lb1 = ax_d1.get_legend_handles_labels()
                h2, lb2 = ax_d2.get_legend_handles_labels()
                ax_d1.legend(h1+h2, lb1+lb2, loc="upper left", fontsize=8)
                plt.tight_layout()

                high_sp_day  = day_grp["平均客単価"].idxmax()
                low_sp_day   = day_grp["平均客単価"].idxmin()
                high_cnt_day = day_grp["来客数"].idxmax()
                results.append({
                    "title": "分析⑤ 曜日別 来客数 × 平均客単価",
                    "image_b64": _fig_to_b64(fig2),
                    "insight": (f"客単価 最高: **{high_sp_day}曜日**（{day_grp.loc[high_sp_day,'平均客単価']:,.0f}円）"
                                f" / 来客数 最多: **{high_cnt_day}曜日**"),
                    "insights": [
                        f"平均客単価 最高の曜日: **{high_sp_day}曜日**（{day_grp.loc[high_sp_day,'平均客単価']:,.0f}円）",
                        f"来客数 最多の曜日: **{high_cnt_day}曜日**（{int(day_grp.loc[high_cnt_day,'来客数'])}件）",
                        f"平均客単価 最低の曜日: **{low_sp_day}曜日** — 単価引き上げ施策の優先ターゲット",
                    ],
                    "advice": [
                        f"高客単価の**{high_sp_day}曜日**には限定メニュー・特別コースを優先展開し、さらに単価を伸ばす",
                        f"低客単価の**{low_sp_day}曜日**はドリンク追加促進・卓上POPでの追加注文声がけを強化する",
                        f"来客数の多い**{high_cnt_day}曜日**に合わせてSNS投稿・キャンペーン告知タイミングを最適化する",
                    ],
                    "table": day_grp.reset_index().rename(columns={"index":"曜日"}).to_dict("records"),
                })

            use_dummy = False
        except Exception:
            pass

    if use_dummy:
        hours_d = list(range(10, 22))
        day_labels_d = ["月","火","水","木","金","土","日"]
        np.random.seed(42)
        dummy_mat = np.array([
            [2,3,5,4,3,2,1,2,3,2,1,1],
            [1,2,4,4,3,2,1,1,2,1,1,0],
            [2,3,5,5,4,3,1,2,3,2,1,1],
            [2,3,6,5,4,3,2,3,4,3,2,1],
            [3,4,7,6,5,4,3,5,6,4,3,2],
            [5,7,9,8,7,6,5,7,8,6,4,3],
            [6,8,10,9,8,7,5,6,7,5,3,2],
        ], dtype=float)
        fig_d, ax_d = plt.subplots(figsize=(11, 3.5))
        im_d = ax_d.imshow(dummy_mat, cmap="YlOrRd", aspect="auto")
        ax_d.set_yticks(range(7))
        ax_d.set_yticklabels(day_labels_d)
        ax_d.set_xticks(range(len(hours_d)))
        ax_d.set_xticklabels([f"{h}時" for h in hours_d], rotation=45, ha="right")
        plt.colorbar(im_d, ax=ax_d, label="来客数", shrink=0.8)
        ax_d.set_title("曜日 × 時間帯別 来客数ヒートマップ ※ダミーデータ")
        plt.tight_layout()
        results.append({
            "title": "分析⑤ 曜日×時間帯 来客数ヒートマップ ※ダミーデータ",
            "image_b64": _fig_to_b64(fig_d),
            "insight": "ダミー例：日曜12時台が最繁忙。土・日・金は終日高水準。",
            "insights": [
                "最繁忙帯: 日曜12時台（ダミー例）— 集中的な人員配置が必要",
                "土・日は終日高い来客数を維持 — 平日との大きな格差あり",
                "火・水の閑散時間帯はタイムセール・SNS集客の好機",
            ],
            "advice": [
                "土・日の繁忙帯にシフトを集中し、提供スピードと回転率を最大化",
                "平日閑散帯に限定割引・セット販売でランチ・おやつ需要を喚起",
                "金曜夜は週末モードの来客が多い — 高価格帯メニューの推奨強化が有効",
            ],
            "table": None,
        })
    return results


# ── 分析⑥ 滞在時間 × 客単価 ──
def analysis_6_stay_time(order_df: pd.DataFrame | None) -> list[dict]:
    results = []
    has_real = (
        order_df is not None
        and "滞在時間_分" in order_df.columns
        and order_df["滞在時間_分"].notna().sum() >= 20
    )

    if has_real:
        stay_df = order_df[(order_df["滞在時間_分"] > 0) & (order_df["滞在時間_分"] <= 360)].copy()
        if len(stay_df) >= 20:
            bins   = [0, 30, 60, 90, 120, 150, 360]
            labels = ["0-30分","30-60分","60-90分","90-120分","120-150分","150分超"]
            stay_df["滞在時間帯"] = pd.cut(stay_df["滞在時間_分"], bins=bins, labels=labels)
            grp = stay_df.groupby("滞在時間帯", observed=True)["客単価"].agg(
                ["mean","count"]
            ).rename(columns={"mean":"平均客単価","count":"件数"})
            grp = grp[grp["件数"] >= 3]

            if len(grp) >= 2:
                stay_center = {"0-30分":0.25,"30-60分":0.75,"60-90分":1.25,
                               "90-120分":1.75,"120-150分":2.25,"150分超":3.0}
                grp["時間客単価"] = [
                    row["平均客単価"] / stay_center.get(str(idx), 1.0)
                    if stay_center.get(str(idx), 0) > 0 else 0
                    for idx, row in grp.iterrows()
                ]

                fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4))
                ax1.bar(grp.index.astype(str), grp["平均客単価"], color="#5b9bd5", edgecolor="white")
                ax1.set_xlabel("滞在時間帯")
                ax1.set_ylabel("平均客単価（円）")
                ax1.set_title("滞在時間帯別 平均客単価")
                ax1.tick_params(axis="x", rotation=20)
                ax2.plot(range(len(grp)), grp["時間客単価"].values, marker="o", color="#e74c3c", linewidth=2)
                ax2.fill_between(range(len(grp)), grp["時間客単価"].values, alpha=0.2, color="#e74c3c")
                ax2.set_xticks(range(len(grp)))
                ax2.set_xticklabels(grp.index.astype(str), rotation=20, ha="right")
                ax2.set_ylabel("時間客単価（円/時間）")
                ax2.set_title("滞在時間帯別 時間客単価")
                plt.tight_layout()

                max_usp_idx = grp["時間客単価"].idxmax()
                max_usp_val = grp.loc[max_usp_idx, "時間客単価"]
                max_sp_idx = grp["平均客単価"].idxmax()
                max_sp_val = grp.loc[max_sp_idx, "平均客単価"]
                results.append({
                    "title": "分析⑥ 滞在時間 × 客単価",
                    "image_b64": _fig_to_b64(fig),
                    "insight": "データには来店・退店時刻が含まれているため、滞在時間に基づく時間客単価を算出しています。",
                    "insights": [
                        f"時間あたり売上効率（時間客単価）が最も高い滞在帯: **{max_usp_idx}**（{max_usp_val:,.0f}円/時）",
                        f"客単価の絶対値が最も高い滞在帯: **{max_sp_idx}**（{max_sp_val:,.0f}円）— 長時間ほど伝票単価は大きい",
                        "短時間帯は時間客単価が高く『効率型』、長時間帯は客単価が高く『高単価型』の2パターンが存在",
                    ],
                    "advice": [
                        f"ピーク時は{max_usp_idx}の回転数を最大化し、時間あたり売上を向上させる",
                        "時間制コース（例: 90分制）の価格を時間客単価に基づいて最適化する",
                        "閑散時は長時間滞在客の追加注文を促す施策（デザート・追加ドリンク声がけ）で高単価化を図る",
                    ],
                    "table": grp.reset_index().to_dict("records"),
                })
                return results

    # ダミー
    stay_bins  = ["0-30分","30-60分","60-90分","90-120分","120-150分","150分超"]
    avg_spend  = [2200, 3400, 4800, 5800, 6500, 7200]
    hourly_usp = [5280, 3400, 2880, 2640, 2340, 2160]
    fig_d, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4))
    ax1.bar(stay_bins, avg_spend, color="#5b9bd5", edgecolor="white")
    ax1.set_xlabel("滞在時間帯")
    ax1.set_ylabel("平均客単価（円）")
    ax1.set_title("滞在時間帯別 平均客単価 ※ダミーデータ（居酒屋想定）")
    ax1.tick_params(axis="x", rotation=25)
    ax2.plot(stay_bins, hourly_usp, marker="o", color="#e74c3c", linewidth=2)
    ax2.fill_between(range(len(stay_bins)), hourly_usp, alpha=0.2, color="#e74c3c")
    ax2.set_xticks(range(len(stay_bins)))
    ax2.set_xticklabels(stay_bins, rotation=25, ha="right")
    ax2.set_ylabel("時間客単価（円/時間）")
    ax2.set_title("滞在時間帯別 時間客単価 ※ダミーデータ（居酒屋想定）")
    plt.tight_layout()
    results.append({
        "title": "分析⑥ 滞在時間 × 客単価 ※ダミーデータ",
        "image_b64": _fig_to_b64(fig_d),
        "insight": "ダミー例：滞在時間が長い客ほど客単価は高いが、時間単位の売上効率は短時間客の方が高い傾向。",
        "insights": [
            "滞在時間が長いほど客単価は上昇するが、時間客単価（効率）は短時間帯が最も高い（ダミー例）",
            "0-30分帯の時間客単価: 約5,280円/時 vs 150分超: 約2,160円/時 — 短時間の方が約2.4倍効率的",
            "高客単価と高時間効率は二律背反 — 戦略的に使い分けることが重要",
        ],
        "advice": [
            "ピーク時（混雑時間帯）は時間制コース・制限を設けて回転率を優先",
            "90分・120分コースの価格は時間客単価に基づいて見直す",
            "閑散時は長時間滞在を歓迎し、追加注文（デザート・締め料理）で客単価を伸ばす施策を展開",
        ],
        "table": None,
    })
    return results


def run_all_analyses(df: pd.DataFrame) -> list[dict]:
    """6項目の分析を一括実行し、結果リストを返す。"""
    order_df = build_order_df(df)
    results = []
    for fn in [
        analysis_1_variable_regression,
        analysis_2_product_regression,
        analysis_3_abc_analysis,
        analysis_4_basket,
        analysis_5_dayhour_heatmap,
        analysis_6_stay_time,
    ]:
        try:
            results.extend(fn(order_df))
        except Exception as e:
            results.append({
                "title": fn.__name__,
                "image_b64": _placeholder_b64(f"エラー: {e}"),
                "insight": str(e),
                "table": None,
            })
    return results
