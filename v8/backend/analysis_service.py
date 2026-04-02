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
plt.rcParams["font.family"] = "DejaVu Sans"  # Railway/Linux fallback
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

    odf = d.groupby(key_col).agg(**agg).reset_index()
    odf.rename(columns={key_col: "注文ID"}, inplace=True)
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
            ("一人単価","一人単価"),("合計数量","合計数量"),
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
                direction = "正の方向（客単価UP）" if vals[0] > 0 else "負の方向（客単価DOWN）"
                results.append({
                    "title": "分析① 客単価への影響度（重回帰分析）",
                    "image_b64": _fig_to_b64(fig),
                    "insight": f"**{top}** が客単価に最も影響しています（{direction}）。",
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
                    insight = ""
                    if pos_items:
                        insight += f"客単価UP商品: {', '.join(pos_items[:3])}。"
                    if neg_items:
                        insight += f" 客単価DOWN商品: {', '.join(neg_items[:3])}。"
                    results.append({
                        "title": "分析② 商品別 客単価への影響度（重回帰分析）",
                        "image_b64": _fig_to_b64(fig),
                        "insight": insight.strip(),
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
            results.append({
                "title": "分析③ ABC分析 - グループ別 平均客単価",
                "image_b64": _fig_to_b64(fig1),
                "insight": (f"全体平均 {avg_all:,.0f}円 | "
                            f"高（A）: {gs.loc['高（A）','平均客単価']:,.0f}円 / "
                            f"低（C）: {gs.loc['低（C）','平均客単価']:,.0f}円"),
                "table": gs.reset_index().to_dict("records"),
            })

            exclude = ["レジ袋","袋","クーポン","割引","引","0円"]
            fig2, axes = plt.subplots(1, 3, figsize=(9, 3.5))
            for idx, (grp, clr) in enumerate([("高（A）","#c0392b"),("中（B）","#e67e22"),("低（C）","#27ae60")]):
                sub = odf[odf["客単価グループ"] == grp]
                items = [it for lst in sub["商品リスト"] for it in lst
                         if it and not any(ex in it for ex in exclude)]
                top5 = [it for it, _ in Counter(items).most_common(5)]
                cnts = [Counter(items)[it] for it in top5]
                axes[idx].barh(top5[::-1], cnts[::-1], color=clr, edgecolor="white")
                axes[idx].set_title(grp, fontsize=9)
                axes[idx].tick_params(axis="y", labelsize=7)
            plt.suptitle("グループ別 売上貢献商品 Top5", fontsize=10)
            plt.tight_layout()
            results.append({
                "title": "分析③ ABC分析 - グループ別 売上貢献商品",
                "image_b64": _fig_to_b64(fig2),
                "insight": "各客単価グループで最も注文されている商品を比較しています。",
                "table": None,
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
            "table": None,
        })
    return results


# ── 分析④ バスケット分析 ──
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

                n = len(top_items)
                mat = np.zeros((n, n))
                item_idx = {it: i for i, it in enumerate(top_items)}
                for (a, b), cnt in pair_count.items():
                    if a in item_idx and b in item_idx:
                        i, j = item_idx[a], item_idx[b]
                        mat[i, j] = cnt
                        mat[j, i] = cnt

                fig, ax = plt.subplots(figsize=(7, 6))
                im = ax.imshow(mat, cmap="YlOrRd", aspect="auto")
                ax.set_xticks(range(n))
                ax.set_yticks(range(n))
                short = [it[:10] for it in top_items]
                ax.set_xticklabels(short, rotation=45, ha="right", fontsize=7)
                ax.set_yticklabels(short, fontsize=7)
                plt.colorbar(im, ax=ax, shrink=0.8)
                ax.set_title("商品共起頻度ヒートマップ")
                plt.tight_layout()

                top_pairs = pair_count.most_common(10)
                pair_table = [{"商品ペア": f"{a} × {b}", "共起件数": cnt}
                               for (a, b), cnt in top_pairs]
                best_insight = ""
                if top_pairs:
                    bp = top_pairs[0]
                    best_insight = f"最多ペア: **{bp[0][0]}** × **{bp[0][1]}**（{bp[1]}件）"

                results.append({
                    "title": "分析④ バスケット分析 - 商品共起頻度ヒートマップ",
                    "image_b64": _fig_to_b64(fig),
                    "insight": best_insight,
                    "table": pair_table,
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
            "table": [{"商品ペア":"バーガー × ドリンク","共起件数":90},
                      {"商品ペア":"バーガー × ポテト","共起件数":85}],
        })
    return results


# ── 分析⑤ ヘビー vs ライト ──
def analysis_5_heavy_light(order_df: pd.DataFrame | None) -> list[dict]:
    results = []
    use_dummy = True

    if (order_df is not None and "ヘビー数" in order_df.columns
            and "ライト数" in order_df.columns and len(order_df) >= 20):
        try:
            odf = order_df.copy()
            def classify(row):
                h, l = row.get("ヘビー数", 0), row.get("ライト数", 0)
                if h == 0 and l == 0:
                    return "その他"
                if h > l:
                    return "ヘビー系"
                if l > h:
                    return "ライト系"
                return "ミックス"
            odf["食品タイプ"] = odf.apply(classify, axis=1)
            grp = (
                odf.groupby("食品タイプ")["客単価"]
                .agg(["mean","median","count"])
                .rename(columns={"mean":"平均客単価","median":"中央値","count":"件数"})
                .loc[lambda d: d["件数"] >= 5]
            )
            if len(grp) >= 2:
                clr_map = {"ヘビー系":"#e74c3c","ライト系":"#27ae60","ミックス":"#e67e22","その他":"#95a5a6"}
                fig, ax = plt.subplots(figsize=(6, 4))
                ax.bar(grp.index, grp["平均客単価"],
                       color=[clr_map.get(g,"#999") for g in grp.index], edgecolor="white")
                ax.set_ylabel("平均客単価（円）")
                ax.set_title("食品タイプ別 平均客単価")
                plt.tight_layout()
                insight = ""
                if "ヘビー系" in grp.index and "ライト系" in grp.index:
                    h_avg = grp.loc["ヘビー系","平均客単価"]
                    l_avg = grp.loc["ライト系","平均客単価"]
                    if h_avg > l_avg:
                        insight = f"ヘビー系客の平均客単価（{h_avg:,.0f}円）はライト系（{l_avg:,.0f}円）より高い傾向。"
                    else:
                        insight = f"ライト系客の平均客単価（{l_avg:,.0f}円）はヘビー系（{h_avg:,.0f}円）より高い傾向。"
                results.append({
                    "title": "分析⑤ 食品タイプ別 平均客単価",
                    "image_b64": _fig_to_b64(fig),
                    "insight": insight,
                    "table": grp.reset_index().to_dict("records"),
                })
                use_dummy = False
        except Exception:
            pass

    if use_dummy:
        types_d = ["ヘビー系","ライト系","ミックス","その他"]
        avg_d   = [3800, 2900, 3200, 2500]
        colors_d = ["#e74c3c","#27ae60","#e67e22","#95a5a6"]
        fig_d, ax_d = plt.subplots(figsize=(6, 4))
        ax_d.bar(types_d, avg_d, color=colors_d, edgecolor="white")
        ax_d.set_ylabel("平均客単価（円）")
        ax_d.set_title("食品タイプ別 平均客単価 ※ダミーデータ")
        plt.tight_layout()
        results.append({
            "title": "分析⑤ 食品タイプ別 平均客単価 ※ダミーデータ",
            "image_b64": _fig_to_b64(fig_d),
            "insight": "ダミー例：ヘビー系（揚げ物・大サイズ）を注文する客は客単価が最も高い傾向。",
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
                ax1.set_title("滞在時間帯別 平均客単価（実データ）")
                ax1.tick_params(axis="x", rotation=20)
                ax2.plot(range(len(grp)), grp["時間客単価"].values, marker="o", color="#e74c3c", linewidth=2)
                ax2.fill_between(range(len(grp)), grp["時間客単価"].values, alpha=0.2, color="#e74c3c")
                ax2.set_xticks(range(len(grp)))
                ax2.set_xticklabels(grp.index.astype(str), rotation=20, ha="right")
                ax2.set_ylabel("時間客単価（円/時間）")
                ax2.set_title("滞在時間帯別 時間客単価（実データ）")
                plt.tight_layout()

                results.append({
                    "title": "分析⑥ 滞在時間 × 客単価（実データ）",
                    "image_b64": _fig_to_b64(fig),
                    "insight": "居酒屋の実際の来店・退店時刻から算出した滞在時間別の客単価と時間効率を表示しています。",
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
        analysis_5_heavy_light,
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
