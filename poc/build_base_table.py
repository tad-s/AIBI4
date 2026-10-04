"""テング池袋東口店 レコメンドPoC — 基礎テーブル構築。

現行 RPC(get_izakaya_sales) は SELECT DISTINCT ON でオーダー粒度を潰すため、
同時/連続オーダー分析には使えない。ここでは生テーブル
(order_items / orders / visits) を直接結合し、要件の除外を適用した
「PoC専用の明細テーブル」を order 粒度で構築する（原本データは保全）。

出力: poc/data/poc_base.parquet（+ funnel をコンソール表示）
実行: v10 の venv 等 pandas/pyarrow のある環境で
      python poc/build_base_table.py
"""
from __future__ import annotations

import csv
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "池袋東口店")
ETC = os.path.join(ROOT, "etc")
OUT_DIR = os.path.join(ROOT, "poc", "data")

# 商品分類器（v10 のロジックを再利用）＋ PoC用カテゴリ手当
sys.path.insert(0, os.path.join(ROOT, "v10", "backend"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ingest.categories import classify, set_master  # noqa: E402
from category_overrides import build_master  # noqa: E402

# item_category_master.sql + PoC手当（POS略称対応）を分類器に注入
set_master(build_master(os.path.join(ETC, "item_category_master.sql")))

# ── 期間・時間帯（要件） ──
PERIOD_START = pd.Timestamp("2026-03-01")
PERIOD_END = pd.Timestamp("2026-06-01")   # 5/31 まで（右端排他）
OPEN_HOUR = 14
CLOSE_HOUR_DEFAULT = 23   # 全日 14:00-23:00
CLOSE_HOUR_SUNDAY = 22    # 日曜のみ 22:00 閉店


def _load_exclusion_names() -> set[str]:
    """定食メニュー.txt と 分析対象外メニュー.csv の商品名集合。"""
    names: set[str] = set()

    teishoku = os.path.join(ETC, "池袋東口店_定食メニュー.txt")
    with open(teishoku, encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            # ヘッダ/注記/箇条書き行を除外し、純粋なメニュー名のみ拾う
            if not s or s.startswith("＜") or s.startswith("・"):
                continue
            names.add(s)

    taigaigai = os.path.join(ETC, "分析対象外メニュー.csv")
    with open(taigaigai, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            nm = (row.get("item_name") or "").strip()
            if nm:
                names.add(nm)
    return names


# お好みコース・飲み放題系のキーワード（明示除外）
_COURSE_KW = ["お好みコース", "飲み放題", "放題", "お好み宴会", "宴会コース"]


def _is_course(name: str) -> bool:
    return any(kw in str(name) for kw in _COURSE_KW)


def build() -> pd.DataFrame:
    oi = pd.read_csv(os.path.join(DATA, "池袋東口店_order_items.csv"), dtype=str)
    vs = pd.read_csv(os.path.join(DATA, "池袋東口店_visits.csv"), dtype=str)

    oi["quantity"] = pd.to_numeric(oi["quantity"], errors="coerce").fillna(0)
    oi["unit_price"] = pd.to_numeric(oi["unit_price"], errors="coerce").fillna(0)
    oi["order_seq"] = pd.to_numeric(oi["order_seq"], errors="coerce")
    oi["ordered_at"] = pd.to_datetime(oi["ordered_at"], errors="coerce")
    vs["party_size"] = pd.to_numeric(vs["party_size"], errors="coerce").fillna(0).astype(int)
    vs["visit_start"] = pd.to_datetime(vs["visit_start"], errors="coerce")

    funnel: list[tuple[str, int, int]] = []

    def log(step: str, df: pd.DataFrame):
        funnel.append((step, len(df), df["visit_id"].nunique()))

    log("生 order_items", oi)

    # 来店属性(party_size, visit_start, receipt_no)を付与
    df = oi.merge(
        vs[["visit_id", "store_id", "receipt_no", "party_size", "visit_start"]],
        on=["visit_id", "store_id"], how="inner",
    )
    log("visits 結合後", df)

    # ① 商品行のみ（S行=無料オプション/トッピングは除外、M行=注文商品）
    df = df[df["line_type"] == "M"].copy()
    log("M行のみ(S除外)", df)

    # ② 期間 2026-03-01〜05-31
    df = df[(df["ordered_at"] >= PERIOD_START) & (df["ordered_at"] < PERIOD_END)]
    log("期間 3-5月", df)

    # ③ 時間帯 14:00-23:00（日曜のみ 14:00-22:00）
    hour = df["ordered_at"].dt.hour
    dow = df["ordered_at"].dt.dayofweek  # 0=月, 6=日
    close = dow.map(lambda d: CLOSE_HOUR_SUNDAY if d == 6 else CLOSE_HOUR_DEFAULT)
    df = df[(hour >= OPEN_HOUR) & (hour < close)]
    log("時間帯 14-23時(日22)", df)

    # ④ メニュー除外（定食 + 対象外CSV）
    excl = _load_exclusion_names()
    before = len(df)
    df = df[~df["item_name"].isin(excl)]
    matched = before - len(df)
    log("定食+対象外CSV 除外", df)

    # ⑤ お好みコース・飲み放題
    df = df[~df["item_name"].map(_is_course)]
    log("コース/放題 除外", df)

    # ⑥ 分類し「除外」カテゴリを落とす（システム項目）
    df["category"] = df["item_name"].map(classify)
    df = df[df["category"] != "除外"]
    log("カテゴリ除外", df)

    # フード/ドリンク フラグ
    df["fd"] = df["category"].map(lambda c: "ドリンク" if c == "ドリンク" else "フード")

    # 出力列を整える
    out = df[[
        "visit_id", "store_id", "receipt_no", "party_size", "visit_start",
        "order_id", "order_seq", "line_index", "ordered_at",
        "item_name", "category", "fd", "quantity", "unit_price",
    ]].reset_index(drop=True)

    # ── funnel 表示 ──
    print("=== 基礎テーブル構築 funnel（行数 / 来店数） ===")
    for step, n, v in funnel:
        print(f"  {step:24s} 行={n:8,d}  来店={v:6,d}")
    print(f"\n除外リスト適用でマッチした行数: {matched:,}")
    print(f"最終: 明細行={len(out):,}  来店={out['visit_id'].nunique():,}  "
          f"オーダー={out['order_id'].nunique():,}  商品種={out['item_name'].nunique():,}")
    print("フード/ドリンク内訳(行):", out["fd"].value_counts().to_dict())

    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, "poc_base.parquet")
    out.to_parquet(path, index=False)
    print(f"\n出力: {path}")
    return out


if __name__ == "__main__":
    build()
