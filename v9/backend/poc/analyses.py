"""テング池袋東口店 PoC — 4分析（v9のベース分析と同じ card 形式を返す）。

card = {title, image_b64, insight, insights, advice, table(list[dict])}
1来店ID = visit_id。同時=同一order_id、連続=隣接order_seq A(前)→B(次)。
"""
from __future__ import annotations

import base64
import io
import platform
from collections import Counter, defaultdict
from itertools import combinations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

if platform.system() == "Windows":
    plt.rcParams["font.family"] = ["Yu Gothic", "Meiryo", "MS Gothic", "DejaVu Sans"]
else:
    plt.rcParams["font.family"] = ["Noto Sans CJK JP", "IPAGothic", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

MIN_TABLES = 10
MIN3 = 5   # 3連鎖の出現閾値（卓数）。まず5卓以上で集計（有効でなければ調整）
_C_DRINK, _C_FOOD, _C_SEQ, _C_CAT = "#5b9bd5", "#f39c12", "#e74c3c", "#7c5cff"
_C_SEQ3 = "#c0392b"


def _b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=140, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def _hbar(ax, labels, values, color, title, xlabel):
    y = range(len(labels))
    ax.barh(list(y), values, color=color)
    ax.set_yticks(list(y))
    ax.set_yticklabels(labels, fontsize=9)
    ax.invert_yaxis()
    ax.set_title(title, fontsize=11, fontweight="bold")
    ax.set_xlabel(xlabel, fontsize=9)
    for i, v in enumerate(values):
        ax.text(v, i, f" {int(v):,}", va="center", fontsize=8)


def _party2(df):
    return df[df["party_size"] >= 2]


def _visits_ge15(df):
    vq = df.groupby("visit_id")["quantity"].sum()
    return df[df["visit_id"].isin(vq[vq >= 15].index)]


def _consecutive(d, col):
    fd = dict(zip(d[col], d["fd"]))
    cnt: Counter = Counter()
    tbl: defaultdict = defaultdict(set)
    og = (d.sort_values(["visit_id", "order_seq"])
            .groupby(["visit_id", "order_seq"])[col]
            .agg(lambda s: list(dict.fromkeys(s))))
    for vid, sub in og.groupby(level=0):
        vals = sub.droplevel(0).sort_index().tolist()
        for i in range(len(vals) - 1):
            for a in vals[i]:
                for b in vals[i + 1]:
                    if a == b:
                        continue
                    cnt[(a, b)] += 1
                    tbl[(a, b)].add(vid)
    return cnt, tbl, fd


# ── #1 注文総数が多い卓の商品TOP10（フード/ドリンク別）──
def analysis1(df):
    d = _visits_ge15(_party2(df))
    g = (d.groupby(["item_name", "fd", "category"])
           .agg(数量=("quantity", "sum"), 卓数=("visit_id", "nunique")).reset_index())
    drink = g[g["fd"] == "ドリンク"].sort_values("数量", ascending=False).head(10)
    food = g[g["fd"] == "フード"].sort_values("数量", ascending=False).head(10)
    overall = g.sort_values("数量", ascending=False).head(10)

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6))
    _hbar(axes[0], drink["item_name"].tolist(), drink["数量"].tolist(), _C_DRINK, "ドリンク TOP10", "合計数量")
    _hbar(axes[1], food["item_name"].tolist(), food["数量"].tolist(), _C_FOOD, "フード TOP10", "合計数量")
    fig.suptitle("PoC① 注文総数が多い卓の商品TOP10（2組以上・15品以上の卓）", fontsize=12, fontweight="bold")
    fig.tight_layout()
    return {
        "title": "PoC① 注文総数が多い卓の商品TOP10",
        "image_b64": _b64(fig),
        "insight": f"対象卓 {d['visit_id'].nunique():,}（2組以上かつ15品以上）。ドリンク首位=**{drink.iloc[0]['item_name']}**／フード首位=**{food.iloc[0]['item_name']}**。",
        "insights": [
            f"ドリンク最多: {drink.iloc[0]['item_name']}（{int(drink.iloc[0]['数量']):,}点）",
            f"フード最多: {food.iloc[0]['item_name']}（{int(food.iloc[0]['数量']):,}点）",
            "合計数量はフード・ドリンクを含む（明細M行）",
        ],
        "advice": [
            "フード上位品をレコメンド核に、ドリンクとのセット提案で単価を伸ばす",
            "高頻度フードを初期メニュー導線の目立つ位置へ",
        ],
        "table": overall[["item_name", "fd", "category", "数量", "卓数"]].to_dict("records"),
        "drill": {"type": "item_hours", "col": "item_name", "label": "時間帯別"},
    }


# ── #2 同時注文ペア TOP10 ──
def analysis2(df):
    d = _party2(df)
    fdmap = dict(zip(d["item_name"], d["fd"]))
    og = d.groupby("order_id").agg(items=("item_name", lambda s: list(dict.fromkeys(s))),
                                   visit_id=("visit_id", "first"))
    cnt: Counter = Counter()
    tbl: defaultdict = defaultdict(set)
    for row in og.itertuples():
        names = row.items
        if not any(fdmap[n] == "フード" for n in names):
            continue
        for a, b in combinations(sorted(set(names)), 2):
            if fdmap[a] == "ドリンク" and fdmap[b] == "ドリンク":
                continue
            cnt[(a, b)] += 1
            tbl[(a, b)].add(row.visit_id)
    rows = [{"商品ペア": f"{a} × {b}", "組合せ": f"{fdmap[a]}×{fdmap[b]}",
             "共起オーダー数": c, "卓数": len(tbl[(a, b)])} for (a, b), c in cnt.items()]
    top = pd.DataFrame(rows).sort_values(["共起オーダー数", "卓数"], ascending=False).head(10)

    fig, ax = plt.subplots(figsize=(11, 4.8))
    _hbar(ax, top["商品ペア"].tolist(), top["共起オーダー数"].tolist(), _C_FOOD,
          "PoC② 同時注文ペア TOP10（同一オーダー内）", "共起オーダー数")
    fig.tight_layout()
    return {
        "title": "PoC② 同時注文ペア TOP10",
        "image_b64": _b64(fig),
        "insight": f"同時注文の最多ペアは **{top.iloc[0]['商品ペア']}**（{int(top.iloc[0]['共起オーダー数'])}オーダー）。",
        "insights": [
            f"最多同時ペア: {top.iloc[0]['商品ペア']}",
            "同一オーダー内・ドリンクのみのオーダーは除外・両方ドリンクの組は対象外",
            "ドリンク×フード / フード×フード を対象",
        ],
        "advice": ["上位ペアをセットメニュー／卓上POP候補に", "注文画面の同時レコメンド枠へ反映"],
        "table": top.to_dict("records"),
    }


# ── #3 連続注文ペア TOP10 ──
def analysis3(df):
    d = _party2(df)
    cnt, tbl, fd = _consecutive(d, "item_name")
    rows = [{"連続ペア": f"{a} → {b}", "組合せ": f"{fd[a]}→{fd[b]}",
             "出現回数": c, "卓数": len(tbl[(a, b)])}
            for (a, b), c in cnt.items() if len(tbl[(a, b)]) >= MIN_TABLES]
    top = pd.DataFrame(rows).sort_values(["卓数", "出現回数"], ascending=False).head(10)

    fig, ax = plt.subplots(figsize=(11, 4.8))
    _hbar(ax, top["連続ペア"].tolist(), top["卓数"].tolist(), _C_SEQ,
          "PoC③ 連続注文ペア TOP10（隣接オーダー A→B・10卓以上）", "卓数")
    fig.tight_layout()
    return {
        "title": "PoC③ 連続注文ペア TOP10",
        "image_b64": _b64(fig),
        "insight": f"最も強い連続注文は **{top.iloc[0]['連続ペア']}**（{int(top.iloc[0]['卓数'])}卓）。",
        "insights": [
            f"最多連続ペア: {top.iloc[0]['連続ペア']}",
            "隣接オーダー間で A(前)→B(次)、有向（A→BとB→Aは別）",
            "10卓以上で出現した組合せのみ",
        ],
        "advice": ["A注文後にBを『次の一手』として提示", "連続ペアをモバイルオーダーの表示順に反映"],
        "table": top.to_dict("records"),
    }


# ── #4 注文継続につながる組み合わせ 各Top5 ──
def analysis4(df):
    d = _visits_ge15(_party2(df))
    cnt, tbl, fd = _consecutive(d, "item_name")
    ip = pd.DataFrame([{"連続ペア": f"{a} → {b}", "fa": fd[a], "fb": fd[b],
                        "出現回数": c, "卓数": len(tbl[(a, b)])}
                       for (a, b), c in cnt.items() if len(tbl[(a, b)]) >= MIN_TABLES])

    def bucket(kind):
        if ip.empty:
            return ip
        if kind == "FF":
            m = (ip["fa"] == "フード") & (ip["fb"] == "フード")
        elif kind == "DD":
            m = (ip["fa"] == "ドリンク") & (ip["fb"] == "ドリンク")
        else:
            m = ip["fa"] != ip["fb"]
        return ip[m].sort_values(["卓数", "出現回数"], ascending=False).head(5)

    ff, dd, fdb = bucket("FF"), bucket("DD"), bucket("FD")

    fig, axes = plt.subplots(1, 3, figsize=(14, 3.8))
    for ax, part, title, color in [
        (axes[0], ff, "フード→フード", _C_FOOD),
        (axes[1], dd, "ドリンク→ドリンク", _C_DRINK),
        (axes[2], fdb, "フード↔ドリンク", _C_SEQ),
    ]:
        if len(part):
            _hbar(ax, part["連続ペア"].tolist(), part["卓数"].tolist(), color, title, "卓数")
        else:
            ax.text(0.5, 0.5, "該当なし", ha="center"); ax.axis("off"); ax.set_title(title)
    fig.suptitle("PoC④ 注文継続につながる商品組み合わせ 各Top5（10卓以上）", fontsize=12, fontweight="bold")
    fig.tight_layout()

    tbl_rows = []
    for name, part in [("フード→フード", ff), ("ドリンク→ドリンク", dd), ("フード↔ドリンク", fdb)]:
        for _, r in part.iterrows():
            tbl_rows.append({"区分": name, "連続ペア": r["連続ペア"], "卓数": int(r["卓数"]), "出現回数": int(r["出現回数"])})

    return {
        "title": "PoC④ 注文継続につながる商品組み合わせ 各Top5",
        "image_b64": _b64(fig),
        "insight": "フード×フード／ドリンク×ドリンク／フード×ドリンクの継続組み合わせを各Top5で抽出（2組以上・15品以上・10卓以上）。",
        "insights": [
            "①〜③と同一母集団（2組以上かつ15品以上）で分析",
            "継続＝隣接オーダー間の A→B（10卓以上）",
        ],
        "advice": [
            "FD（フード↔ドリンク）継続の上位を『次の一杯／一品』提案に活用",
            "フード→フード継続はコース/おすすめ導線の設計に反映",
        ],
        "table": tbl_rows,
    }


# ── #4 カテゴリ版（継続をカテゴリ粒度で）──
def analysis4_category(df):
    d = _visits_ge15(_party2(df))
    cnt, tbl, _ = _consecutive(d, "category")
    rows = [{"カテゴリ連続": f"{a} → {b}", "出現回数": c, "卓数": len(tbl[(a, b)])}
            for (a, b), c in cnt.items() if len(tbl[(a, b)]) >= MIN_TABLES]
    top = pd.DataFrame(rows).sort_values(["卓数", "出現回数"], ascending=False).head(12)

    fig, ax = plt.subplots(figsize=(11, 5))
    _hbar(ax, top["カテゴリ連続"].tolist(), top["卓数"].tolist(), _C_CAT,
          "PoC④(カテゴリ) 注文継続の組み合わせ（カテゴリ粒度・10卓以上）", "卓数")
    fig.tight_layout()
    return {
        "title": "PoC④(カテゴリ) 注文継続の組み合わせ",
        "image_b64": _b64(fig),
        "insight": f"カテゴリ継続の最多は **{top.iloc[0]['カテゴリ連続']}**（{int(top.iloc[0]['卓数'])}卓）。",
        "insights": [
            "商品名では埋もれる傾向をカテゴリ粒度で可視化",
            "『1杯目の後に何のカテゴリが続くか』を示す",
        ],
        "advice": ["継続の強いカテゴリを次オーダーの推奨カテゴリに設定", "例: ドリンク→揚げ物／ヘビー の導線強化"],
        "table": top.to_dict("records"),
        "drill": {"type": "category_pair", "col": "カテゴリ連続", "label": "内訳を見る"},
    }


# ══════════ 3品版（別指標）: 直積＋卓数、5卓以上でまず集計 ══════════
def _consecutive3(d, col):
    """隣接3オーダーの A→B→C（有向・直積）。1オーダーに複数カテゴリがあれば全組合せ。"""
    fd = dict(zip(d[col], d["fd"]))
    cnt: Counter = Counter()
    tbl: defaultdict = defaultdict(set)
    og = (d.sort_values(["visit_id", "order_seq"])
            .groupby(["visit_id", "order_seq"])[col]
            .agg(lambda s: list(dict.fromkeys(s))))
    for vid, sub in og.groupby(level=0):
        vals = sub.droplevel(0).sort_index().tolist()
        for i in range(len(vals) - 2):
            for a in vals[i]:
                for b in vals[i + 1]:
                    if a == b:
                        continue
                    for c in vals[i + 2]:
                        if b == c:
                            continue
                        cnt[(a, b, c)] += 1
                        tbl[(a, b, c)].add(vid)
    return cnt, tbl, fd


def _seq3_frame(d, col):
    cnt, tbl, fd = _consecutive3(d, col)
    rows = [{"連続3品": f"{a} → {b} → {c}", "組合せ": f"{fd[a]}→{fd[b]}→{fd[c]}",
             "出現回数": v, "卓数": len(tbl[(a, b, c)])}
            for (a, b, c), v in cnt.items() if len(tbl[(a, b, c)]) >= MIN3]
    if not rows:
        return pd.DataFrame(columns=["連続3品", "組合せ", "出現回数", "卓数"])
    return pd.DataFrame(rows).sort_values(["卓数", "出現回数"], ascending=False).reset_index(drop=True)


def _seq3_card(top, card_title, chart_title, color, level_note, advice, drill=None):
    fig, ax = plt.subplots(figsize=(12, 5))
    if len(top):
        _hbar(ax, top["連続3品"].head(12).tolist(), top["卓数"].head(12).tolist(), color, chart_title, "卓数")
    else:
        ax.text(0.5, 0.5, f"{MIN3}卓以上の3連鎖なし", ha="center", va="center")
        ax.axis("off"); ax.set_title(chart_title)
    fig.tight_layout()
    head = top.iloc[0]["連続3品"] if len(top) else "該当なし"
    return {
        "title": card_title,
        "image_b64": _b64(fig),
        "insight": (f"最も多い3連続注文は **{head}**（{int(top.iloc[0]['卓数'])}卓）。"
                    if len(top) else f"{MIN3}卓以上の3連鎖は見つかりませんでした（閾値調整の余地）。"),
        "insights": [
            "隣接する3オーダー(前→中→次)の A→B→C。有向・直積・卓数で順位付け。",
            f"{level_note}　閾値: {MIN3}卓以上。",
        ],
        "advice": advice,
        "table": top.head(12).to_dict("records"),
        **({"drill": drill} if drill else {}),
    }


def analysis5_seq3_item(df):
    top = _seq3_frame(_party2(df), "item_name")
    return _seq3_card(
        top, "PoC⑤ 連続注文3品（商品）", "PoC⑤ 連続注文3品（商品 A→B→C・5卓以上）", _C_SEQ3,
        "母集団: 2組以上（#3連続ペアと同じ）。商品名粒度。",
        ["A→Bの後の3品目Cを『次の一手』として提示", "3連鎖上位をコース/セット設計に反映"])


def analysis6_seq3_category(df):
    top = _seq3_frame(_visits_ge15(_party2(df)), "category")
    return _seq3_card(
        top, "PoC⑥ 連続注文3品（カテゴリ）", "PoC⑥ 連続注文3品（カテゴリ A→B→C・5卓以上）", _C_CAT,
        "母集団: 2組以上かつ15品以上（#4カテゴリと同じ）。カテゴリ粒度。",
        ["ドリンク→○→○ の定番フローを推奨導線に", "3カテゴリの流れをコース構成に反映"],
        drill={"type": "category_seq3", "col": "連続3品", "label": "内訳を見る"})


def analysis7_coorder3_item(df):
    d = _party2(df)
    fdmap = dict(zip(d["item_name"], d["fd"]))
    og = d.groupby("order_id").agg(items=("item_name", lambda s: list(dict.fromkeys(s))),
                                   visit_id=("visit_id", "first"))
    cnt: Counter = Counter()
    tbl: defaultdict = defaultdict(set)
    for row in og.itertuples():
        names = row.items
        if len(names) < 3 or not any(fdmap[n] == "フード" for n in names):
            continue
        for trio in combinations(sorted(set(names)), 3):
            if all(fdmap[x] == "ドリンク" for x in trio):
                continue
            cnt[trio] += 1
            tbl[trio].add(row.visit_id)
    rows = [{"商品3組": f"{a} × {b} × {c}", "共起オーダー数": v, "卓数": len(tbl[(a, b, c)])}
            for (a, b, c), v in cnt.items()]
    top = (pd.DataFrame(rows).sort_values(["共起オーダー数", "卓数"], ascending=False).reset_index(drop=True)
           if rows else pd.DataFrame(columns=["商品3組", "共起オーダー数", "卓数"]))
    fig, ax = plt.subplots(figsize=(12, 5))
    if len(top):
        _hbar(ax, top["商品3組"].head(10).tolist(), top["共起オーダー数"].head(10).tolist(),
              _C_FOOD, "PoC⑦ 同時注文3品（同一オーダー内・商品）", "共起オーダー数")
    else:
        ax.text(0.5, 0.5, "該当なし", ha="center", va="center"); ax.axis("off"); ax.set_title("PoC⑦ 同時注文3品")
    fig.tight_layout()
    head = top.iloc[0]["商品3組"] if len(top) else "該当なし"
    return {
        "title": "PoC⑦ 同時注文3品（商品）",
        "image_b64": _b64(fig),
        "insight": (f"最も多い同時3品は **{head}**（{int(top.iloc[0]['共起オーダー数'])}オーダー）。"
                    if len(top) else "該当する同時3品はありませんでした。"),
        "insights": [
            "同一order_id内の3品組み合わせ（#2同時ペアの3品版）。",
            "ドリンクのみのオーダー・3品すべてドリンクは除外（1品以上フード）。母集団: 2組以上。",
        ],
        "advice": ["同時3品の上位を3点セット/盛合せ候補に", "卓上POP・レコメンドの3点提案に活用"],
        "table": top.head(12).to_dict("records"),
    }


def run_poc_analyses(df: pd.DataFrame) -> list[dict]:
    out = []
    for fn in [analysis1, analysis2, analysis3, analysis4, analysis4_category,
               analysis5_seq3_item, analysis6_seq3_category, analysis7_coorder3_item]:
        try:
            out.append(fn(df))
        except Exception as e:  # noqa: BLE001
            out.append({"title": f"{fn.__name__} エラー", "image_b64": "",
                        "insight": f"計算エラー: {e}", "insights": [], "advice": [], "table": None})
    return out
