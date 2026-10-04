"""汎用カテゴリ付与。

PoC用に精緻化した分類器(poc.classify + item_category_master.sql)を、
通常のチャット/ベース分析データ(全店舗)にも流用してカテゴリ列を付与する。
PoC専用テーブルは使わない（商品名→カテゴリの純粋な写像のみ利用）。行は落とさない。
"""
from __future__ import annotations

import os

import pandas as pd

from poc.classify import classify, set_master
from poc.overrides import build_master

_ETC = os.path.join(
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")), "etc")
# マスタSQLの探索順: ①コード同梱(本番Railwayイメージに必ず入る) → ②リポジトリの etc/。
# Dockerfile.v9 は etc/ をコピーしないため、同梱コピーが無いとクラウドで master が空になり
# POS略称(サイコロステ/ナカ 等)の完全一致分類が全滅する。build_master は SQL が無くても
# POC_OVERRIDES を返すので、両方欠けてもキーワード分類で動作は継続する。
_MASTER_CANDIDATES = (
    os.path.join(os.path.dirname(__file__), "item_category_master.sql"),  # 同梱
    os.path.join(_ETC, "item_category_master.sql"),                        # リポetc
)
_INIT = False


def _ensure_master() -> None:
    global _INIT
    if not _INIT:
        sql_path = next((p for p in _MASTER_CANDIDATES if os.path.exists(p)), None)
        try:
            set_master(build_master(sql_path))  # sql_path=None でも POC_OVERRIDES は効く
        except Exception:  # noqa: BLE001  マスタが無くてもキーワード分類で動く
            set_master({})
        _INIT = True


def categorize(name) -> str:
    _ensure_master()
    c = classify(name)
    return "その他" if c == "除外" else c  # 通常データでは行を落とさずラベルのみ


def add_categories(df: pd.DataFrame, name_col: str = "商品名") -> pd.DataFrame:
    """df に『カテゴリ』(11分類)と『フードドリンク』(ドリンク/フード)列を付与して返す。"""
    if name_col not in df.columns:
        return df
    _ensure_master()
    cat = df[name_col].map(categorize)
    df["カテゴリ"] = cat
    df["フードドリンク"] = cat.map(lambda c: "ドリンク" if c == "ドリンク" else "フード")
    return df
