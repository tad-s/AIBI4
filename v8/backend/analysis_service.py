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

# ── キーワード辞書（優先順: 締め > ドリンク > 揚げ物 > 串 > 海鮮 > 鍋 > サラダ > ヘビー > 軽いつまみ） ──
_DRINK_KW = [
    "ビール","生ビール","生中","生大","ハイボール","チューハイ","酎ハイ",
    "サワー","レモンサワー","梅サワー","ワイン","日本酒","冷酒","熱燗",
    "焼酎","麦焼酎","芋焼酎","泡盛","ホッピー","カクテル","梅酒",
    "ウーロン茶","お茶","緑茶","麦茶","コーラ","ジュース",
    "ソフトドリンク","ノンアルコール","ノンアル","ドリンク","ソーダ",
    # 略称・省略形カバー
    "ハイ","サワ","麦酒","ビア","ホッピ","ジョッキ","赤星","黒ラベル",
    "ジンジャ","カシス","ロック","水割","お冷","ジャスミン",
]
_SHIME_KW = [  # 締め（最優先）
    "ラーメン","うどん","そば","チャーハン","炒飯","焼きそば",
    "おにぎり","ご飯","雑炊","ちゃんぽん","カレー",
    "焼き飯","焼飯","冷麺","蕎麦","パスタ","ナポリタン",
    "ドリア","オムライス","ライス","釜飯","釜めし",
]
_AGEMON_KW = [  # 揚げ物
    "唐揚げ","から揚げ","フライドチキン","揚げ","揚",
    "天ぷら","フライ","コロッケ","カツ","トンカツ","南蛮",
    "串カツ","串揚げ",
]
_KUSHI_KW = [  # 串
    "焼き鳥","焼鳥","串焼き","串",
    "つくね","ねぎま",
]
_KAISEN_KW = [  # 海鮮
    "刺身","刺し身","お刺身","刺し",
    "カルパッチョ","マリネ",
    "海老","えび","蟹","かに","たこ","いか","イカ",
    "まぐろ","マグロ","サーモン","鮭","魚介","ホタテ","貝","あさり","牡蠣",
    "海鮮","なめろ","たこわさ","いかわさ",
]
_NABE_KW = [  # 鍋
    "鍋","おでん","しゃぶ","すき焼","チゲ",
]
_SALAD_KW = [  # サラダ
    "サラダ","チョレギ",
]
_HEAVY_KW = [  # ヘビーフード（揚げ物・串・海鮮・鍋以外の主菜系）
    "焼肉","ステーキ","ハラミ","カルビ",
    "豚バラ","ロース","ネギ塩","もも",
    "鉄板","炒め","煮込み","もつ煮","煮込",
    "餃子","ピザ","グラタン",
]
_LIGHT_KW = [  # 軽いつまみ（サラダ・海鮮以外の小皿系）
    "野菜","枝豆","漬物","キムチ","冷奴","豆腐",
    "おひたし","和え物","小鉢","酢の物",
    "アヒージョ","ナムル","ポテサラ","玉子","卵焼き","しらす",
    "ナム","漬け","生ハム","ポン酢",
]


def _kw_match(name, kw_list) -> bool:
    if pd.isna(name):
        return False
    return any(kw in str(name) for kw in kw_list)


def _normalize_name(name: str) -> str:
    """ひらがなをカタカナに変換してキーワードマッチ精度を上げる。"""
    return "".join(chr(ord(c) + 0x60) if 0x3041 <= ord(c) <= 0x3096 else c for c in name)


# 商品カテゴリマスタ（Supabase の item_category_master テーブルから起動時に取得）
_ITEM_CATEGORY_MASTER: dict[str, str] = {}


def set_item_category_master(d: dict[str, str]) -> None:
    """data_router からデータ取得後に呼び出してマスタをセットする。"""
    global _ITEM_CATEGORY_MASTER
    _ITEM_CATEGORY_MASTER = d


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
    # マスタで「除外」指定されたアイテム（モバイルオーダー等）を除去
    if "商品名" in d.columns and _ITEM_CATEGORY_MASTER:
        d = d[d["商品名"].apply(lambda x: _get_item_category(str(x)) if pd.notna(x) else "その他") != "除外"].copy()
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
        # _get_item_category を使って分類（全カテゴリ体系と一致させる）
        _cats = d["商品名"].apply(lambda x: _get_item_category(str(x)) if pd.notna(x) else "その他")
        d["_is_drink"] = (_cats == "ドリンク").astype(int)
        # ヘビー系=揚げ物・串・海鮮・鍋・ヘビーの合算（FD比率算出に使用）
        _food_cats = {"揚げ物", "串", "海鮮", "鍋", "ヘビー"}
        d["_is_heavy"] = _cats.isin(_food_cats).astype(int)
        d["_is_light"] = _cats.isin({"軽いつまみ", "サラダ"}).astype(int)

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


# ════════════════════════════════════════════════════════════════
# 注文シナリオ分析（A〜G）
# order_time（注文日時）が必要な分析は izakaya / cafe データのみ対応。
# ════════════════════════════════════════════════════════════════

_CAT_ORDER = [
    "ドリンク", "揚げ物", "串", "海鮮", "鍋", "サラダ", "ヘビー", "軽いつまみ", "締め", "その他",
]
_CAT_COLORS = {
    "ドリンク":   "#5b9bd5",
    "揚げ物":     "#f39c12",
    "串":         "#e74c3c",
    "海鮮":       "#1abc9c",
    "鍋":         "#e67e22",
    "サラダ":     "#70ad47",
    "ヘビー":     "#c0392b",
    "軽いつまみ": "#2ecc71",
    "締め":       "#9b59b6",
    "その他":     "#95a5a6",
}


def _get_item_category(name: str) -> str:
    """商品名からカテゴリを返す。マスタ優先 → 正規化後キーワードマッチ。"""
    if pd.isna(name):
        return "その他"
    name_str = str(name)
    # 1. マスタテーブル完全一致（最優先）
    if name_str in _ITEM_CATEGORY_MASTER:
        return _ITEM_CATEGORY_MASTER[name_str]
    # 2. ひらがな→カタカナ正規化（¶うーろん茶 → ¶ウーロン茶 等）
    norm = _normalize_name(name_str)
    # 3. キーワードマッチ（締め → ドリンク → 揚げ物 → 串 → 海鮮 → 鍋 → サラダ → ヘビー → 軽いつまみ）
    if _kw_match(norm, _SHIME_KW):   return "締め"
    if _kw_match(norm, _DRINK_KW):   return "ドリンク"
    if _kw_match(norm, _AGEMON_KW):  return "揚げ物"
    if _kw_match(norm, _KUSHI_KW):   return "串"
    if _kw_match(norm, _KAISEN_KW):  return "海鮮"
    if _kw_match(norm, _NABE_KW):    return "鍋"
    if _kw_match(norm, _SALAD_KW):   return "サラダ"
    if _kw_match(norm, _HEAVY_KW):   return "ヘビー"
    if _kw_match(norm, _LIGHT_KW):   return "軽いつまみ"
    return "その他"


def _build_order_waves_df(df: pd.DataFrame):
    """注文日時ベースで _visit_key / _wave_no / _category を付与したDFを返す。
    注文日時列がない or 有効値が 10 件未満の場合は None。"""
    if "注文日時" not in df.columns:
        return None
    ot = pd.to_datetime(df["注文日時"], errors="coerce")
    if ot.notna().sum() < 10:
        return None

    d = df.copy()
    d["注文日時"] = ot
    d["_category"] = d["商品名"].apply(
        lambda x: _get_item_category(str(x)) if pd.notna(x) else "その他"
    )
    # マスタで「除外」に設定されたアイテム（モバイルオーダー等）を除去
    d = d[d["_category"] != "除外"].copy()
    if "来店時間" in d.columns:
        d["_visit_key"] = (
            d["来店時間"].astype(str).fillna("?") + "_" + d["伝票番号"].astype(str)
        )
    else:
        d["_visit_key"] = d["伝票番号"].astype(str)

    def _assign(grp):
        valid = grp["注文日時"].dropna().sort_values().unique()
        t2w   = {t: i + 1 for i, t in enumerate(valid)}
        g     = grp.copy()
        g["_wave_no"] = g["注文日時"].map(
            lambda t: t2w.get(t, 0) if pd.notna(t) else 0
        )
        return g

    d = d.groupby("_visit_key", group_keys=False).apply(_assign)
    d = d[d["_wave_no"] > 0].reset_index(drop=True)
    return d if len(d) >= 10 else None


def _no_order_time(title: str) -> list[dict]:
    return [{
        "title": title,
        "image_b64": _placeholder_b64(
            "この分析は izakaya / cafe データのみ対応\n（注文日時情報が必要です）"
        ),
        "insight": "注文日時データがないため分析できません（izakaya/cafe を選択してください）。",
        "insights": ["izakaya / cafe データセットを選択すると表示されます。"],
        "advice": [],
        "table": None,
        "evidence_tables": [],
    }]


# ── 分析A: 売れるメニューの組み合わせ ────────────────────────────────
def analysis_menu_combinations(df: pd.DataFrame) -> list[dict]:
    """同一ラウンドの同時注文ペア TOP10 と、次ラウンドへの連続注文ペア TOP10。"""
    waves = _build_order_waves_df(df)
    if waves is None:
        return _no_order_time("分析A 売れるメニューの組み合わせ")

    sim_cnt: Counter = Counter()
    seq_cnt: Counter = Counter()
    sim_den: Counter = Counter()
    seq_den: Counter = Counter()

    for vk, grp in waves.groupby("_visit_key"):
        w_items: dict = {}
        for wno, wg in grp.groupby("_wave_no"):
            items = set(wg["商品名"].dropna().astype(str).tolist())
            w_items[wno] = items

        wkeys = sorted(w_items)
        for wno in wkeys:
            items = list(w_items[wno])
            for itm in items:
                sim_den[itm] += 1
            for a, b in combinations(set(items), 2):
                a, b = tuple(sorted([a, b]))
                sim_cnt[(a, b)] += 1
        for i in range(len(wkeys) - 1):
            cur = w_items[wkeys[i]]
            nxt = w_items[wkeys[i + 1]]
            for itm in cur:
                seq_den[itm] += 1
            for a in cur:
                for b in nxt:
                    if a != b:
                        seq_cnt[(a, b)] += 1

    top_sim = sim_cnt.most_common(10)
    top_seq = seq_cnt.most_common(10)

    fig1, ax1 = plt.subplots(figsize=(9, 5))
    if top_sim:
        lbls1 = [f"{a} × {b}" for (a, b), _ in top_sim]
        vals1 = [cnt / max(sim_den.get(a, 1), 1) * 100 for (a, b), cnt in top_sim]
        ax1.barh(lbls1[::-1], vals1[::-1], color="#5b9bd5", edgecolor="white")
        for y, v in enumerate(vals1[::-1]):
            ax1.text(v + 0.4, y, f"{v:.1f}%", va="center", fontsize=9)
        ax1.set_xlim(0, max(vals1) * 1.3)
    ax1.set_xlabel("同時注文率（%）")
    ax1.set_title("同時注文ペア TOP10（同一ラウンドで一緒に注文される割合）")
    plt.tight_layout()

    ev_sim = [
        {"商品ペア": f"{a} × {b}", "同時注文件数": cnt,
         "同時注文率(%)": round(cnt / max(sim_den.get(a, 1), 1) * 100, 1)}
        for (a, b), cnt in top_sim
    ]

    fig2, ax2 = plt.subplots(figsize=(9, 5))
    if top_seq:
        lbls2 = [f"{a} → {b}" for (a, b), _ in top_seq]
        vals2 = [cnt / max(seq_den.get(a, 1), 1) * 100 for (a, b), cnt in top_seq]
        ax2.barh(lbls2[::-1], vals2[::-1], color="#e74c3c", edgecolor="white")
        for y, v in enumerate(vals2[::-1]):
            ax2.text(v + 0.4, y, f"{v:.1f}%", va="center", fontsize=9)
        ax2.set_xlim(0, max(vals2) * 1.3)
    ax2.set_xlabel("連続注文率（%）")
    ax2.set_title("連続注文ペア TOP10（前ラウンドのAの次にBが注文される割合）")
    plt.tight_layout()

    ev_seq = [
        {"先行商品": a, "次に注文": b, "連続件数": cnt,
         "連続注文率(%)": round(cnt / max(seq_den.get(a, 1), 1) * 100, 1)}
        for (a, b), cnt in top_seq
    ]

    top1_sim = f"{top_sim[0][0][0]} × {top_sim[0][0][1]}" if top_sim else "—"
    top1_seq = f"{top_seq[0][0][0]} → {top_seq[0][0][1]}" if top_seq else "—"
    r1_sim   = ev_sim[0]["同時注文率(%)"] if ev_sim else 0
    r1_seq   = ev_seq[0]["連続注文率(%)"] if ev_seq else 0

    return [
        {
            "title": "分析A 同時注文ペア TOP10",
            "image_b64": _fig_to_b64(fig1),
            "insight": f"最多同時ペア: {top1_sim}（{r1_sim:.1f}%）",
            "insights": [
                f"No.1 同時ペア: **{top_sim[0][0][0]}** × **{top_sim[0][0][1]}**（同時率 {r1_sim:.1f}%）" if top_sim else "データなし",
                "同一ラウンドで一緒に注文されるペア = セット推奨・卓上POPに最適",
            ],
            "advice": [
                "上位ペアをセットメニューや追加推奨スクリプトに組み込む",
                "ドリンク×フードの同時ペアはファーストオーダー誘導に特に有効",
            ],
            "table": ev_sim[:5],
            "evidence_tables": [{"title": "同時注文ペア全件", "records": ev_sim}],
        },
        {
            "title": "分析A 連続注文ペア TOP10",
            "image_b64": _fig_to_b64(fig2),
            "insight": f"最多連続ペア: {top1_seq}（{r1_seq:.1f}%）",
            "insights": [
                f"No.1 連続ペア: **{top_seq[0][0][0]}** → **{top_seq[0][0][1]}**（連続率 {r1_seq:.1f}%）" if top_seq else "データなし",
                "次ラウンドで何が注文されやすいか = 追加注文推奨の具体的材料",
            ],
            "advice": [
                "先行商品が注文されたら連続ペアの商品を次ラウンドで口頭推奨する",
                "連続率の高い組み合わせはコースメニューの順序設計に活用できる",
            ],
            "table": ev_seq[:5],
            "evidence_tables": [{"title": "連続注文ペア全件", "records": ev_seq}],
        },
    ]


# ── 分析B: 注文の流れ ──────────────────────────────────────────────
def analysis_order_flow(df: pd.DataFrame) -> list[dict]:
    """ラウンド別カテゴリ構成比（積み上げ棒）と主要遷移パターン。"""
    waves = _build_order_waves_df(df)
    if waves is None:
        return _no_order_time("分析B 注文の流れ")

    def wave_grp(n):
        if n == 1: return "1ラウンド目"
        if n == 2: return "2ラウンド目"
        if n == 3: return "3ラウンド目"
        return "4ラウンド目以降"

    waves["_wgrp"] = waves["_wave_no"].apply(wave_grp)
    w_order = ["1ラウンド目", "2ラウンド目", "3ラウンド目", "4ラウンド目以降"]

    pivot = waves.groupby(["_wgrp", "_category"]).size().unstack(fill_value=0)
    pivot = pivot.reindex(columns=[c for c in _CAT_ORDER if c in pivot.columns], fill_value=0)
    pct   = pivot.div(pivot.sum(axis=1), axis=0) * 100
    pct   = pct.reindex([w for w in w_order if w in pct.index])

    fig1, ax1 = plt.subplots(figsize=(9, 5))
    bot = np.zeros(len(pct))
    for cat in pct.columns:
        color = _CAT_COLORS.get(cat, "#95a5a6")
        bars  = ax1.bar(pct.index, pct[cat], bottom=bot, label=cat, color=color)
        for bar, b in zip(bars, bot):
            h = bar.get_height()
            if h > 7:
                ax1.text(bar.get_x() + bar.get_width() / 2, b + h / 2,
                         f"{h:.0f}%", ha="center", va="center", fontsize=8, color="white")
        bot += pct[cat].values
    ax1.set_xlabel("注文ラウンド")
    ax1.set_ylabel("割合 (%)")
    ax1.set_title("注文ラウンド別 カテゴリ構成比")
    ax1.legend(loc="upper right", fontsize=8)
    ax1.set_ylim(0, 108)
    plt.tight_layout()

    trans: Counter = Counter()
    for vk, grp in waves.groupby("_visit_key"):
        dom = (
            grp.sort_values("_wave_no")
            .groupby("_wave_no")["_category"]
            .apply(lambda s: Counter(s).most_common(1)[0][0])
        )
        wns = sorted(dom.index)
        for i in range(len(wns) - 1):
            trans[(dom[wns[i]], dom[wns[i + 1]])] += 1

    top_trans = trans.most_common(8)
    total_tr  = sum(trans.values()) or 1

    fig2, ax2 = plt.subplots(figsize=(9, 5))
    if top_trans:
        tlbls = [f"{a} → {b}" for (a, b), _ in top_trans]
        tvals = [cnt / total_tr * 100 for _, cnt in top_trans]
        tcols = [_CAT_COLORS.get(b, "#95a5a6") for (a, b), _ in top_trans]
        ax2.barh(tlbls[::-1], tvals[::-1], color=tcols[::-1], edgecolor="white")
        for y, v in enumerate(tvals[::-1]):
            ax2.text(v + 0.3, y, f"{v:.1f}%", va="center", fontsize=9)
        ax2.set_xlim(0, max(tvals) * 1.3)
    ax2.set_xlabel("遷移割合（全遷移中の%）")
    ax2.set_title("カテゴリ遷移パターン TOP8")
    plt.tight_layout()

    ev_pct = pct.reset_index().rename(columns={"_wgrp": "ラウンド"}).round(1).to_dict("records")
    ev_tr  = [{"遷移": f"{a}→{b}", "件数": cnt, "割合(%)": round(cnt / total_tr * 100, 1)}
              for (a, b), cnt in top_trans]

    d1_pct = float(pct.loc["1ラウンド目", "ドリンク"]) if "1ラウンド目" in pct.index and "ドリンク" in pct.columns else 0
    top_tr = top_trans[0] if top_trans else (("—", "—"), 0)
    avg_w  = float(waves.groupby("_visit_key")["_wave_no"].max().mean())

    insights = [
        f"1ラウンド目: ドリンク **{d1_pct:.0f}%** — 来店直後は飲み物が最優先",
        f"最多遷移パターン: **{top_tr[0][0]} → {top_tr[0][1]}** ({top_tr[1] / total_tr * 100:.1f}%)",
        f"平均注文ラウンド数: {avg_w:.1f} ラウンド / 来店",
    ]
    advice = [
        "1ラウンド目でドリンクのみ注文の客へフードを声がけし、2ラウンド継続率を引き上げる",
        f"最多遷移「{top_tr[0][0]} → {top_tr[0][1]}」を基本推奨シナリオとしてスタッフに共有する",
    ]

    return [
        {
            "title": "分析B 注文の流れ — ラウンド別カテゴリ構成",
            "image_b64": _fig_to_b64(fig1),
            "insight": f"1ラウンド目: ドリンク {d1_pct:.0f}%。最多遷移: {top_tr[0][0]}→{top_tr[0][1]}",
            "insights": insights,
            "advice": advice,
            "table": ev_pct,
            "evidence_tables": [{"title": "ラウンド別カテゴリ構成比(%)", "records": ev_pct}],
        },
        {
            "title": "分析B 注文の流れ — カテゴリ遷移パターン",
            "image_b64": _fig_to_b64(fig2),
            "insight": f"最多遷移: {top_tr[0][0]} → {top_tr[0][1]} ({top_tr[1] / total_tr * 100:.1f}%)",
            "insights": insights,
            "advice": advice,
            "table": ev_tr,
            "evidence_tables": [{"title": "カテゴリ遷移パターン", "records": ev_tr}],
        },
    ]


# ── 分析C: 初期注文の影響 ──────────────────────────────────────────
def analysis_first_order_impact(df: pd.DataFrame) -> list[dict]:
    """1ラウンド目の内容が総注文品数・客単価に与える影響。"""
    waves = _build_order_waves_df(df)
    if waves is None:
        return _no_order_time("分析C 初期注文の影響")

    fw      = waves[waves["_wave_no"] == 1]
    fw_cats = fw.groupby("_visit_key")["_category"].apply(lambda s: frozenset(s.unique()))

    def _cls(cats):
        has_d = "ドリンク" in cats
        has_f = bool(cats - {"ドリンク", "その他"})
        if has_d and has_f: return "ドリンク＋フード"
        if has_d:           return "ドリンクのみ"
        if has_f:           return "フードのみ"
        return "その他"

    fw_pat = fw_cats.apply(_cls)
    qty_col = "数量" if "数量" in waves.columns else None
    v_items = waves.groupby("_visit_key")[qty_col].sum() if qty_col else waves.groupby("_visit_key")["商品名"].count()

    combined = pd.DataFrame({"items": v_items, "pattern": fw_pat}).dropna()

    if "合計金額(税込)" in df.columns:
        if "来店時間" in df.columns:
            _vk = df["来店時間"].astype(str).fillna("?") + "_" + df["伝票番号"].astype(str)
        else:
            _vk = df["伝票番号"].astype(str)
        spend = df.assign(_vk=_vk).drop_duplicates(subset=["_vk"]).set_index("_vk")["合計金額(税込)"]
        combined["spend"] = spend

    pat_order = ["ドリンクのみ", "ドリンク＋フード", "フードのみ", "その他"]
    pats      = [p for p in pat_order if p in combined["pattern"].values]
    grp_i     = combined.groupby("pattern")["items"].agg(["mean", "count"]).reindex(pats)

    n_cols = 2 if "spend" in combined.columns else 1
    fig, axes = plt.subplots(1, n_cols, figsize=(11 if n_cols == 2 else 7, 5))
    if n_cols == 1:
        axes = [axes]

    pal  = {"ドリンクのみ": "#5b9bd5", "ドリンク＋フード": "#70ad47", "フードのみ": "#e74c3c", "その他": "#95a5a6"}
    cols = [pal.get(p, "#95a5a6") for p in pats]

    bars0 = axes[0].bar(pats, grp_i["mean"], color=cols, edgecolor="white")
    for bar in bars0:
        axes[0].text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.05,
                     f"{bar.get_height():.1f}品", ha="center", va="bottom", fontsize=9)
    axes[0].set_xlabel("初期注文パターン")
    axes[0].set_ylabel("平均総注文品数")
    axes[0].set_title("初期注文パターン別 平均総注文品数")
    plt.setp(axes[0].get_xticklabels(), rotation=20, ha="right")

    if "spend" in combined.columns:
        grp_s = combined.groupby("pattern")["spend"].mean().reindex(pats)
        bars1 = axes[1].bar(pats, grp_s, color=cols, edgecolor="white")
        for bar in bars1:
            axes[1].text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 100,
                         f"¥{bar.get_height():,.0f}", ha="center", va="bottom", fontsize=9)
        axes[1].set_xlabel("初期注文パターン")
        axes[1].set_ylabel("平均客単価（円）")
        axes[1].set_title("初期注文パターン別 平均客単価")
        plt.setp(axes[1].get_xticklabels(), rotation=20, ha="right")
    plt.tight_layout()

    ev = []
    for p in pats:
        row = {"初期注文パターン": p,
               "件数": int(grp_i.loc[p, "count"]),
               "平均注文品数": round(float(grp_i.loc[p, "mean"]), 2)}
        if "spend" in combined.columns:
            row["平均客単価(円)"] = round(float(combined[combined["pattern"] == p]["spend"].mean()), 0)
        ev.append(row)

    best = grp_i["mean"].idxmax() if not grp_i.empty else "—"
    bv   = float(grp_i["mean"].max()) if not grp_i.empty else 0

    return [{
        "title": "分析C 初期注文の影響",
        "image_b64": _fig_to_b64(fig),
        "insight": f"初期「{best}」で最も多く注文（平均 {bv:.1f} 品）",
        "insights": [
            f"初期パターン「**{best}**」の来店客は平均 {bv:.1f} 品と最も多く注文",
            "ドリンク＋フードで始めるとその後の注文が伸びる傾向",
            "「ドリンクのみ」スタートの客へのフード追加誘導が最重要施策",
        ],
        "advice": [
            "ファーストオーダーでドリンク＋フードを同時に取るよう声がけを標準化する",
            "「まずはこちらもどうぞ」形式で初期セット推奨を卓上POPで補強する",
        ],
        "table": ev,
        "evidence_tables": [{"title": "初期注文パターン別集計", "records": ev}],
    }]


# ── 分析D: 注文の連鎖条件 ──────────────────────────────────────────
def analysis_order_chain(df: pd.DataFrame) -> list[dict]:
    """ラウンド数分布とラウンド間継続確率（離脱ポイント可視化）。"""
    waves = _build_order_waves_df(df)
    if waves is None:
        return _no_order_time("分析D 注文の連鎖条件")

    v_max = waves.groupby("_visit_key")["_wave_no"].max()
    total = len(v_max)
    max_w = min(int(v_max.max()), 6)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    reach = [(v_max >= n).mean() * 100 for n in range(1, max_w + 1)]
    xlbls = [f"{n}R" for n in range(1, max_w + 1)]
    rcols = ["#5b9bd5" if n <= 2 else "#e74c3c" if n <= 4 else "#9b59b6" for n in range(1, max_w + 1)]
    bars1 = ax1.bar(xlbls, reach, color=rcols, edgecolor="white")
    for bar, v in zip(bars1, reach):
        ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                 f"{v:.1f}%", ha="center", va="bottom", fontsize=9)
    ax1.set_xlabel("ラウンド数")
    ax1.set_ylabel("到達率 (%)")
    ax1.set_title("Nラウンド以上注文した来店客の割合")
    ax1.set_ylim(0, 115)

    cprobs = []
    for n in range(1, max_w):
        rn  = (v_max >= n).sum()
        rn1 = (v_max >= n + 1).sum()
        cprobs.append(rn1 / rn * 100 if rn > 0 else 0)

    if cprobs:
        x2 = [f"{n}→{n+1}R" for n in range(1, max_w)]
        ax2.plot(range(len(x2)), cprobs, marker="o", color="#e74c3c", linewidth=2.5, zorder=5)
        ax2.fill_between(range(len(x2)), cprobs, alpha=0.15, color="#e74c3c")
        for i, v in enumerate(cprobs):
            ax2.annotate(f"{v:.1f}%", (i, v), xytext=(0, 8), textcoords="offset points",
                         ha="center", fontsize=9)
        ax2.set_xticks(range(len(x2)))
        ax2.set_xticklabels(x2, rotation=20, ha="right")
    ax2.set_ylabel("継続確率 (%)")
    ax2.set_title("ラウンド間継続確率（N→N+1ラウンドへ進む割合）")
    ax2.set_ylim(0, 105)
    plt.tight_layout()

    avg_w  = float(v_max.mean())
    drop1  = cprobs[0] if cprobs else 0
    wdist  = v_max.value_counts().sort_index()

    if cprobs:
        min_i    = int(np.argmin(cprobs))
        drop_pt  = min_i + 1
        drop_val = 100 - cprobs[min_i]
    else:
        drop_pt, drop_val = 1, 0

    ev_dist = [{"ラウンド数": int(k), "件数": int(v), "割合(%)": round(v / total * 100, 1)} for k, v in wdist.items()]
    ev_cont = [{"遷移": f"{n}→{n+1}R", "継続確率(%)": round(cprobs[n - 1], 1)} for n in range(1, max_w)]

    return [{
        "title": "分析D 注文の連鎖条件",
        "image_b64": _fig_to_b64(fig),
        "insight": f"平均 {avg_w:.1f} ラウンド / 来店。1→2R 継続率: {drop1:.1f}%",
        "insights": [
            f"平均 **{avg_w:.1f} ラウンド** / 来店",
            f"1→2ラウンド継続率: **{drop1:.1f}%** — ここが最大の離脱ポイント",
            f"最大脱落: **{drop_pt}→{drop_pt + 1}ラウンド** ({drop_val:.1f}%が次ラウンドに進まない)",
        ],
        "advice": [
            "最初のオーダー後すぐに追加注文の声がけを行い、2ラウンド目を確保する",
            "2ラウンド目を取れた客はそれ以降も継続しやすい — 初動声がけに集中投資する",
        ],
        "table": ev_cont,
        "evidence_tables": [
            {"title": "ラウンド数分布", "records": ev_dist},
            {"title": "ラウンド間継続確率", "records": ev_cont},
        ],
    }]


# ── 分析E: 時間帯別の違い ──────────────────────────────────────────
def analysis_timeslot_ordering(df: pd.DataFrame) -> list[dict]:
    """時間帯（来店時間）別の平均注文品数・客単価・カテゴリ構成比。"""
    if "来店時間" not in df.columns or df["来店時間"].isna().all():
        return _no_order_time("分析E 時間帯別の違い")

    d = df.copy()
    d["_hour"] = pd.to_datetime(d["来店時間"], errors="coerce").dt.hour
    d = d.dropna(subset=["_hour"])
    if len(d) < 10:
        return _no_order_time("分析E 時間帯別の違い")

    d["_category"]  = d["商品名"].apply(
        lambda x: _get_item_category(str(x)) if pd.notna(x) else "その他"
    )
    d["_visit_key"] = d["来店時間"].astype(str).fillna("?") + "_" + d["伝票番号"].astype(str)

    qty_col = "数量" if "数量" in d.columns else None
    v_items = d.groupby("_visit_key")[qty_col].sum() if qty_col else d.groupby("_visit_key")["商品名"].count()
    v_hour  = d.drop_duplicates(subset=["_visit_key"]).set_index("_visit_key")["_hour"]
    hour_df = pd.DataFrame({"hour": v_hour, "items": v_items}).dropna()

    if "合計金額(税込)" in d.columns:
        v_spend = d.drop_duplicates(subset=["_visit_key"]).set_index("_visit_key")["合計金額(税込)"]
        hour_df["spend"] = v_spend

    hgrp = hour_df.groupby("hour").agg(avg_items=("items", "mean"), n=("items", "count"))
    if "spend" in hour_df.columns:
        hgrp["avg_spend"] = hour_df.groupby("hour")["spend"].mean()

    d2     = d.merge(v_hour.rename("hour").reset_index(), on="_visit_key", how="left")
    cp     = d2.groupby(["hour", "_category"]).size().unstack(fill_value=0)
    cp     = cp.reindex(columns=[c for c in _CAT_ORDER if c in cp.columns], fill_value=0)
    cp_pct = cp.div(cp.sum(axis=1), axis=0) * 100

    hours = sorted(hgrp.index)
    xlbls = [f"{h}時" for h in hours]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 9))

    ax1r = ax1.twinx()
    ax1.bar(xlbls, hgrp.loc[hours, "avg_items"], color="#5b9bd5", alpha=0.75, label="平均注文品数")
    for i, v in enumerate(hgrp.loc[hours, "avg_items"]):
        ax1.text(i, v + 0.05, f"{v:.1f}", ha="center", va="bottom", fontsize=8)
    if "avg_spend" in hgrp.columns:
        ax1r.plot(xlbls, hgrp.loc[hours, "avg_spend"], marker="o", color="#e74c3c",
                  linewidth=2, label="平均客単価")
        ax1r.set_ylabel("平均客単価（円）", color="#e74c3c")
    ax1.set_ylabel("平均注文品数")
    ax1.set_title("時間帯別 平均注文品数 × 平均客単価")
    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax1r.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=8)
    plt.setp(ax1.get_xticklabels(), rotation=30, ha="right")

    cp_s = cp_pct.reindex(sorted(cp_pct.index))
    x2l  = [f"{h}時" for h in cp_s.index]
    bot2 = np.zeros(len(cp_s))
    for cat in cp_s.columns:
        ax2.bar(x2l, cp_s[cat], bottom=bot2, label=cat, color=_CAT_COLORS.get(cat, "#95a5a6"))
        for i, (v, b) in enumerate(zip(cp_s[cat], bot2)):
            if v > 9:
                ax2.text(i, b + v / 2, f"{v:.0f}%", ha="center", va="center", fontsize=7, color="white")
        bot2 += cp_s[cat].values
    ax2.set_xlabel("来店時間帯")
    ax2.set_ylabel("割合 (%)")
    ax2.set_title("時間帯別 注文カテゴリ構成比")
    ax2.legend(loc="upper right", fontsize=8)
    ax2.set_ylim(0, 108)
    plt.setp(ax2.get_xticklabels(), rotation=30, ha="right")
    plt.tight_layout()

    peak_h = int(hgrp["avg_items"].idxmax()) if not hgrp.empty else 0
    peak_v = float(hgrp["avg_items"].max())   if not hgrp.empty else 0

    ev_hour = []
    for h in hours:
        row = {"時間帯": f"{h}時台", "平均注文品数": round(float(hgrp.loc[h, "avg_items"]), 2),
               "来客数": int(hgrp.loc[h, "n"])}
        if "avg_spend" in hgrp.columns:
            row["平均客単価(円)"] = round(float(hgrp.loc[h, "avg_spend"]), 0)
        ev_hour.append(row)

    ev_cat = cp_pct.reset_index().rename(columns={"hour": "時間帯(時)"}).round(1).to_dict("records")

    return [{
        "title": "分析E 時間帯別の違い",
        "image_b64": _fig_to_b64(fig),
        "insight": f"注文ピーク: {peak_h}時台（平均 {peak_v:.1f} 品）",
        "insights": [
            f"注文品数ピーク: **{peak_h}時台**（平均 {peak_v:.1f} 品）",
            "時間帯によってカテゴリ構成が異なる — 早い時間帯はドリンク中心、遅くなるほどフード比率が上昇",
        ],
        "advice": [
            f"{peak_h}時台はドリンク消費が速いため、追加注文の声がけ間隔を短めに設定する",
            "20時以降はフードと締め料理の推奨を重点的に行う",
        ],
        "table": ev_hour,
        "evidence_tables": [
            {"title": "時間帯別集計", "records": ev_hour},
            {"title": "時間帯別カテゴリ構成(%)", "records": ev_cat},
        ],
    }]


# ── 分析F: 注文が止まるポイント ─────────────────────────────────────
def analysis_order_stoppage(df: pd.DataFrame) -> list[dict]:
    """伝票あたり注文品数の分布と、ラウンドごとの継続率（脱落可視化）。"""
    waves = _build_order_waves_df(df)
    if waves is None:
        return _no_order_time("分析F 注文が止まるポイント")

    qty_col = "数量" if "数量" in waves.columns else None
    v_items = waves.groupby("_visit_key")[qty_col].sum() if qty_col else waves.groupby("_visit_key")["商品名"].count()
    v_max   = waves.groupby("_visit_key")["_wave_no"].max()
    max_w   = min(int(v_max.max()), 6)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    q95     = float(v_items.quantile(0.95))
    clipped = v_items.clip(upper=q95)
    bins    = max(10, int(q95 / 2))
    ax1.hist(clipped, bins=bins, color="#5b9bd5", edgecolor="white", alpha=0.8)
    ax1r = ax1.twinx()
    sv   = np.sort(v_items.values)
    cu   = np.arange(1, len(sv) + 1) / len(sv) * 100
    ax1r.plot(sv, cu, color="#e74c3c", linewidth=1.5, linestyle="--")
    ax1r.set_ylabel("累積 (%)", color="#e74c3c")
    p50 = float(np.percentile(v_items, 50))
    p80 = float(np.percentile(v_items, 80))
    ax1.axvline(p50, color="#e67e22", linestyle=":", linewidth=1.5, label=f"中央値={p50:.0f}品")
    ax1.axvline(p80, color="#c0392b", linestyle=":", linewidth=1.5, label=f"80%ile={p80:.0f}品")
    ax1.set_xlabel("総注文品数")
    ax1.set_ylabel("来店件数")
    ax1.set_title("伝票あたり注文品数の分布")
    ax1.legend(fontsize=8)

    stay  = [(v_max >= n).mean() * 100 for n in range(1, max_w + 1)]
    xlbls = [f"{n}R" for n in range(1, max_w + 1)]
    scols = ["#5b9bd5" if n <= 2 else "#e74c3c" for n in range(1, max_w + 1)]
    ax2.bar(xlbls, stay, color=scols, edgecolor="white")
    for i, v in enumerate(stay):
        ax2.text(i, v + 0.5, f"{v:.1f}%", ha="center", va="bottom", fontsize=9)
    for i in range(len(stay) - 1):
        drop = stay[i] - stay[i + 1]
        ax2.annotate(f"↓{drop:.1f}%",
                     xy=(i + 0.5, (stay[i] + stay[i + 1]) / 2),
                     fontsize=7, ha="center", color="#c0392b")
    ax2.set_ylabel("継続率 (%)")
    ax2.set_title("ラウンドごとの注文継続率")
    ax2.set_ylim(0, 115)
    plt.tight_layout()

    drops = [(n, stay[n - 1] - stay[n]) for n in range(1, max_w)]
    md    = max(drops, key=lambda x: x[1]) if drops else (1, 0)
    drop_pt, drop_val = md[0], md[1]

    med = float(np.median(v_items))
    avg = float(v_items.mean())

    ev_stat = [
        {"統計": "中央値（品数）", "値": round(med, 1)},
        {"統計": "平均（品数）",   "値": round(avg, 1)},
        {"統計": "50%ile",         "値": round(p50, 1)},
        {"統計": "80%ile",         "値": round(p80, 1)},
    ]
    ev_stay = [{"ラウンド": f"{n}R", "継続率(%)": round(stay[n - 1], 1)} for n in range(1, max_w + 1)]

    return [{
        "title": "分析F 注文が止まるポイント",
        "image_b64": _fig_to_b64(fig),
        "insight": f"中央値 {med:.0f} 品。最大脱落: {drop_pt}→{drop_pt + 1}R ({drop_val:.1f}%脱落)",
        "insights": [
            f"注文品数の中央値: **{med:.0f} 品**。80% の来店客は {p80:.0f} 品以下で終了",
            f"最大脱落ポイント: **{drop_pt}→{drop_pt + 1}ラウンド** ({drop_val:.1f}%が次ラウンドに進まない)",
            "このタイミングへの追加声がけが客単価最大化のカギ",
        ],
        "advice": [
            f"{drop_pt}ラウンド目終了後に積極的な追加推奨を行う",
            "中央値未満で終わった客へのアフターフォロー（締め推奨など）で客単価を底上げする",
        ],
        "table": ev_stay,
        "evidence_tables": [
            {"title": "注文品数分布統計", "records": ev_stat},
            {"title": "ラウンド継続率", "records": ev_stay},
        ],
    }]


# ── 分析G: 顧客セグメント × 注文シナリオ ──────────────────────────────
def analysis_segment_scenario(df: pd.DataFrame) -> list[dict]:
    """客層別の注文ラウンド数・初期注文パターン構成比。"""
    waves = _build_order_waves_df(df)
    if waves is None or "客層" not in df.columns:
        return _no_order_time("分析G 顧客セグメント × 注文シナリオ")

    df2 = df.copy()
    if "来店時間" in df2.columns:
        df2["_vk"] = df2["来店時間"].astype(str).fillna("?") + "_" + df2["伝票番号"].astype(str)
    else:
        df2["_vk"] = df2["伝票番号"].astype(str)

    v_seg = df2.drop_duplicates(subset=["_vk"]).set_index("_vk")["客層"]
    v_max = waves.groupby("_visit_key")["_wave_no"].max()

    seg_df = pd.DataFrame({"max_wave": v_max, "seg": v_seg}).dropna(subset=["max_wave"])
    seg_df["seg"] = seg_df["seg"].fillna("不明")
    if seg_df.empty:
        return _no_order_time("分析G 顧客セグメント × 注文シナリオ（客層データ不足）")

    seg_grp = (
        seg_df.groupby("seg")
        .agg(avg_wave=("max_wave", "mean"), n=("max_wave", "count"))
        .sort_values("avg_wave", ascending=False)
    )

    fw      = waves[waves["_wave_no"] == 1]
    fw_cats = fw.groupby("_visit_key")["_category"].apply(lambda s: frozenset(s.unique()))

    def _cls(cats):
        has_d = "ドリンク" in cats
        has_f = bool(cats - {"ドリンク", "その他"})
        if has_d and has_f: return "ドリンク＋フード"
        if has_d:           return "ドリンクのみ"
        return "フード系/その他"

    fw_pat    = fw_cats.apply(_cls)
    ps_df     = pd.DataFrame({"pattern": fw_pat, "seg": v_seg}).dropna(subset=["pattern"])
    ps_df["seg"] = ps_df["seg"].fillna("不明")
    cross     = ps_df.groupby(["seg", "pattern"]).size().unstack(fill_value=0)
    pat_order = ["ドリンク＋フード", "ドリンクのみ", "フード系/その他"]
    cross     = cross.reindex(columns=[p for p in pat_order if p in cross.columns], fill_value=0)
    cross_pct = cross.div(cross.sum(axis=1), axis=0) * 100
    cross_pct = cross_pct.reindex(seg_grp.index, fill_value=0)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    seg_pal = {"VIP": "#c0392b", "会員": "#e67e22", "リピーター": "#27ae60",
               "新規": "#5b9bd5", "一般": "#95a5a6"}
    scols = [seg_pal.get(s, "#95a5a6") for s in seg_grp.index]

    bars1 = ax1.bar(seg_grp.index, seg_grp["avg_wave"], color=scols, edgecolor="white")
    for bar in bars1:
        ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.03,
                 f"{bar.get_height():.1f}", ha="center", va="bottom", fontsize=9)
    ax1.set_xlabel("客層")
    ax1.set_ylabel("平均注文ラウンド数")
    ax1.set_title("客層別 平均注文ラウンド数")

    pat_pal = {"ドリンク＋フード": "#70ad47", "ドリンクのみ": "#5b9bd5", "フード系/その他": "#e74c3c"}
    bot2    = np.zeros(len(cross_pct))
    for pat in cross_pct.columns:
        ax2.bar(cross_pct.index, cross_pct[pat], bottom=bot2,
                label=pat, color=pat_pal.get(pat, "#95a5a6"))
        bot2 += cross_pct[pat].values
    ax2.set_xlabel("客層")
    ax2.set_ylabel("割合 (%)")
    ax2.set_title("客層別 初期注文パターン構成比")
    ax2.legend(loc="upper right", fontsize=8)
    ax2.set_ylim(0, 108)
    plt.tight_layout()

    top_s = seg_grp.index[0] if not seg_grp.empty else "—"
    top_v = float(seg_grp.iloc[0]["avg_wave"]) if not seg_grp.empty else 0
    low_s = seg_grp.index[-1] if len(seg_grp) > 1 else "—"
    low_v = float(seg_grp.iloc[-1]["avg_wave"]) if len(seg_grp) > 1 else 0

    ev_seg = (
        seg_grp.reset_index()
        .rename(columns={"seg": "客層", "avg_wave": "平均ラウンド数", "n": "件数"})
        .round(2).to_dict("records")
    )
    ev_pat = cross_pct.reset_index().rename(columns={"seg": "客層"}).round(1).to_dict("records")

    return [{
        "title": "分析G 顧客セグメント × 注文シナリオ",
        "image_b64": _fig_to_b64(fig),
        "insight": f"最多ラウンド: {top_s}（{top_v:.1f}R）。最少: {low_s}（{low_v:.1f}R）",
        "insights": [
            f"**{top_s}** 客層が最も多くのラウンドを注文（平均 {top_v:.1f} ラウンド）",
            f"**{low_s}** 客層は平均 {low_v:.1f} ラウンドで最も早く注文が止まる — 追加誘導のポテンシャル大",
            "客層ごとに初期注文パターンが異なる — 接客アプローチの差別化が有効",
        ],
        "advice": [
            f"「{low_s}」客にはファーストオーダー後すぐにフードを提案し、ラウンド数を引き上げる",
            f"「{top_s}」の注文パターンをモデルケースとして接客マニュアルに組み込む",
        ],
        "table": ev_seg,
        "evidence_tables": [
            {"title": "客層別注文ラウンド集計", "records": ev_seg},
            {"title": "客層別初期パターン構成比(%)", "records": ev_pat},
        ],
    }]


def run_all_analyses(df: pd.DataFrame) -> list[dict]:
    """既存6項目 + 注文シナリオ分析 A〜G の合計13項目を一括実行する。"""
    order_df = build_order_df(df)
    results: list[dict] = []

    # 既存分析 ①②③⑤⑥（④ basket は新分析 A に置き換え）
    for fn in [
        analysis_1_variable_regression,
        analysis_2_product_regression,
        analysis_3_abc_analysis,
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
                "insights": [str(e)],
                "advice": [],
                "table": None,
                "evidence_tables": [],
            })

    # 注文シナリオ分析 A〜G（order_time 必要 / izakaya・cafe のみ有効）
    for fn in [
        analysis_menu_combinations,
        analysis_order_flow,
        analysis_first_order_impact,
        analysis_order_chain,
        analysis_timeslot_ordering,
        analysis_order_stoppage,
        analysis_segment_scenario,
    ]:
        try:
            results.extend(fn(df))
        except Exception as e:
            results.append({
                "title": fn.__name__,
                "image_b64": _placeholder_b64(f"エラー: {e}"),
                "insight": str(e),
                "insights": [str(e)],
                "advice": [],
                "table": None,
                "evidence_tables": [],
            })

    return results
