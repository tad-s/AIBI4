"""PoC のデータ来歴（エビデンス）テキスト生成とカテゴリ内訳。

原本CSV(order_items/orders/visits)の各カラムが、どんな結合・除外・集計を経て
各分析結果になったかをテキストで開示する（エビデンスDL用）。
"""
from __future__ import annotations

import pandas as pd

# 原本 → 基礎テーブルの来歴（固定パイプライン）
_PIPELINE = [
    ("原本テーブル", "order_items(order_item_id,order_id,visit_id,store_id,order_seq,line_index,"
                "ordered_at,item_name,line_type,quantity,unit_price) と "
                "visits(visit_id,store_id,receipt_no,party_size,visit_start,visit_end) の2つ。"
                "※order_id/order_seq/ordered_at は order_items に含まれるため orders テーブルは不使用。"),
    ("結合", "order_items を visits に (visit_id,store_id) で内部結合し、来店属性"
             "(receipt_no,party_size,visit_start)を付与。1来店ID=visit_id(源泉UUID)。"),
    ("除外1: 明細種別", "line_type='M'(実注文品)のみ採用。'S'(大盛り等の無料オプション)は除外。"),
    ("除外2: 期間", "ordered_at が 2026-03-01〜05-31 の行のみ。"),
    ("除外3: 時間帯", "ordered_at の時刻が 14:00-23:00（日曜のみ14:00-22:00）の行のみ。"),
    ("除外4: メニュー", "定食メニュー(池袋東口店_定食メニュー.txt)・分析対象外メニュー.csv・"
                    "お好みコース/飲み放題・商品名に「宴」(宴会系)/「ＦＤ」(飲み放題) を含むもの に該当する item_name を除外。"),
    ("分類", "item_name → category(ドリンク/揚げ物/串/海鮮/鍋/サラダ/ヘビー/軽いつまみ/締め/デザート/その他)。"
            "キーワード＋POS略称手当。category='除外'(システム項目)を落とす。"
            "fd = category=='ドリンク' ? 'ドリンク' : 'フード'。"),
    ("格納", "上記を PoC専用テーブル poc_ikebukuro_items(order粒度) に保存。原本は不変。"),
]

# 各分析の集計ロジック（title → 説明）
_ANALYSIS_LOGIC = {
    "PoC① 注文総数が多い卓の商品TOP10":
        ("母集団: party_size>=2 かつ 来店(visit_id)合計 quantity>=15 の来店。\n"
         "  集計: item_name×fd×category ごとに quantity 合計・visit_id ユニーク数。数量降順TOP10。"
         "フード/ドリンク別にも同順で抽出。"),
    "PoC② 同時注文ペア TOP10":
        ("母集団: party_size>=2。\n"
         "  同一 order_id 内の item を重複除去し、フードを1品も含まないオーダーは除外。"
         "無向ペア(A,B)を作り、両方ドリンクの組は除外。ペアごとに共起オーダー数・卓(visit)数。降順TOP10。"),
    "PoC③ 連続注文ペア TOP10":
        ("母集団: party_size>=2。\n"
         "  visit_id ごとに order_seq 昇順で隣接オーダー(前→次)を取り、前の品A×次の品Bの有向ペア"
         "(A→B と B→A は別)を作る。10卓(visit)以上のペアのみ。卓数降順TOP10。"),
    "PoC④ 注文継続につながる商品組み合わせ 各Top5":
        ("母集団: party_size>=2 かつ 合計quantity>=15（①〜③と同一母集団）。\n"
         "  ③と同じ隣接オーダーの有向ペアを、フード→フード/ドリンク→ドリンク/フード↔ドリンク の"
         "3区分に分け各Top5(10卓以上)。"),
    "PoC④(カテゴリ) 注文継続の組み合わせ":
        ("母集団: party_size>=2 かつ 合計quantity>=15。\n"
         "  隣接オーダーの有向ペアを category 粒度で集計(10卓以上)。卓数降順TOP。"),
    "PoC⑤ 連続注文3品（商品）":
        ("母集団: party_size>=2。\n"
         "  visit_id ごとに order_seq 昇順で隣接3オーダー(前→中→次)を取り、商品 A→B→C の有向3連鎖を"
         "直積(各オーダーの複数品の全組合せ)で作る。隣接同一(A=B,B=C)は除外。5卓以上・卓数降順TOP。"),
    "PoC⑥ 連続注文3品（カテゴリ）":
        ("母集団: party_size>=2 かつ 合計quantity>=15。\n"
         "  ⑤と同じ隣接3オーダーの A→B→C を category 粒度で集計。直積・5卓以上・卓数降順TOP。"),
    "PoC⑦ 同時注文3品（商品）":
        ("母集団: party_size>=2。\n"
         "  同一 order_id 内の商品を重複除去し、3品の組合せ(無向)を作る。"
         "フードを1品も含まない/3品すべてドリンクのオーダーは除外。共起オーダー数降順TOP。"),
}


def build_evidence_text(df: pd.DataFrame, results: list[dict], meta: dict) -> str:
    L: list[str] = []
    L.append("=" * 64)
    L.append("テング酒場 池袋東口店 レコメンドPoC — エビデンス（データ来歴）ログ")
    L.append("=" * 64)
    L.append(f"対象店舗 : {meta.get('store', '')}")
    L.append(f"対象期間 : {meta.get('period', '')}")
    L.append(f"データ源 : {meta.get('source', 'poc_ikebukuro_items')}")
    L.append(f"母集団   : 明細 {len(df):,}行 / 来店 {df['visit_id'].nunique():,} / "
             f"オーダー {df['order_id'].nunique():,} / 商品 {df['item_name'].nunique():,}種")
    L.append(f"除外条件 : {meta.get('note', '')}")
    L.append("")
    L.append("■ 1. 原本CSVカラム → 基礎テーブルへの来歴（決定論的パイプライン）")
    for i, (step, desc) in enumerate(_PIPELINE, 1):
        L.append(f"  ({i}) [{step}] {desc}")
    L.append("")
    L.append("■ 2. カテゴリ内訳（現時点。編集で変わる）")
    for row in category_breakdown(df)["categories"]:
        L.append(f"  - {row['category']}({row['fd']}): {row['item_count']}品 / "
                 f"数量{int(row['total_qty']):,} / 上位: "
                 f"{'、'.join(x['item_name'] for x in row['items'][:5])}")
    L.append("")
    L.append("■ 3. 各分析の集計ロジックと主要結果")
    for r in results:
        title = r.get("title", "")
        L.append(f"\n【{title}】")
        logic = _ANALYSIS_LOGIC.get(title, r.get("evidence", ""))
        if logic:
            L.append("  " + logic.replace("\n", "\n  "))
        insight = r.get("insight", "")
        if insight:
            L.append("  結果: " + insight.replace("**", ""))
        tbl = r.get("table") or []
        if tbl:
            L.append(f"  出力テーブル({len(tbl)}行)先頭:")
            keys = list(tbl[0].keys())
            L.append("    " + " | ".join(keys))
            for rec in tbl[:5]:
                L.append("    " + " | ".join(str(rec.get(k, "")) for k in keys))
    L.append("")
    L.append("※ 原本(visits/orders/order_items)は一切変更していません（PoC専用テーブルのみ使用）。")
    return "\n".join(L)


def category_breakdown(df: pd.DataFrame) -> dict:
    """category → 所属itemと数量。ドリルダウン/内訳表示用。"""
    cats = []
    g = df.groupby("category")
    order = (g["quantity"].sum().sort_values(ascending=False)).index
    for cat in order:
        sub = df[df["category"] == cat]
        items = (sub.groupby("item_name")
                    .agg(qty=("quantity", "sum"), lines=("item_name", "count"),
                         visits=("visit_id", "nunique"))
                    .reset_index().sort_values("qty", ascending=False))
        cats.append({
            "category": cat,
            "fd": "ドリンク" if cat == "ドリンク" else "フード",
            "item_count": int(len(items)),
            "total_qty": float(sub["quantity"].sum()),
            "total_visits": int(sub["visit_id"].nunique()),
            "items": [{"item_name": r.item_name, "qty": float(r.qty),
                       "lines": int(r.lines), "visits": int(r.visits)}
                      for r in items.itertuples(index=False)],
        })
    return {"categories": cats}
