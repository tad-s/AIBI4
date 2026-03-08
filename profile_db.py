# profile_db.py
import sqlite3
from pathlib import Path
from datetime import datetime

import pandas as pd

# DBはこのファイルと同じフォルダに profile.db で作成
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "profile.db"


def get_conn() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def init_db() -> None:
    """プロファイルDBを初期化（なければ作成）。"""
    conn = get_conn()
    cur = conn.cursor()

    # 店舗マスタ
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS stores (
            shop_code TEXT PRIMARY KEY,
            name TEXT,
            prefecture_id TEXT,
            city TEXT,
            address TEXT
        )
        """
    )

    # 商品マスタ（仮：あとで実データに合わせて拡張可）
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS products (
            product_code TEXT PRIMARY KEY,
            product_name TEXT,
            category TEXT,
            price INTEGER
        )
        """
    )

    # 売上履歴テーブル（前年比・長期分析用の“器”）
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS sales_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_label TEXT,      -- 任意の名前（例: 2025-09）
            file_name TEXT,        -- 元CSVファイル名
            uploaded_at TEXT,      -- 取り込み日時(ISO8601文字列)

            注文日時 TEXT,
            店舗コード TEXT,
            店舗名   TEXT,
            商品明細_TOメニューID TEXT,
            商品名 TEXT,
            合計金額税込 TEXT,
            合計金額税抜 TEXT
        )
        """
    )

    conn.commit()
    conn.close()


# ========= マスタ共通の保存・読み込み =========
def save_master(table_name: str, df: pd.DataFrame, key_column: str) -> None:
    """
    マスタ用DataFrameをSQLiteに保存する。
    既存レコードは全削除してから入れ直し。
    CSV側に余計な列があっても、
    テーブル側に存在する列だけを使ってINSERTする。
    """
    conn = get_conn()
    cur = conn.cursor()

    # テーブルのカラム情報を取得
    cur.execute(f"PRAGMA table_info({table_name})")
    table_cols = [row[1] for row in cur.fetchall()]  # row[1] がカラム名

    if not table_cols:
        conn.close()
        raise RuntimeError(
            f"テーブル {table_name} が存在しません。init_db() が呼ばれているか確認してください。"
        )

    # CSVの列のうち、テーブルに存在する列だけ残す
    use_cols = [c for c in df.columns if c in table_cols]
    if not use_cols:
        conn.close()
        raise RuntimeError(f"CSV にテーブル {table_name} の列が含まれていません。")

    df2 = df[use_cols].copy()

    # 一旦全削除してから入れ直す（差し替え運用）
    cur.execute(f"DELETE FROM {table_name}")
    df2.to_sql(table_name, conn, if_exists="append", index=False)

    conn.commit()
    conn.close()


def load_master(table_name: str) -> pd.DataFrame | None:
    """マスタをDataFrameとして読み込む（まだ無ければ None を返す）。"""
    conn = get_conn()
    try:
        df = pd.read_sql_query(f"SELECT * FROM {table_name}", conn)
    except Exception:
        df = None
    conn.close()
    return df


# ========= プロファイルテキスト生成 =========
def build_profile_summary() -> str:
    """
    LLMに渡す「事前プロファイル」のテキストを組み立てる。
    （店舗数・商品数・代表的な名称など）
    """
    lines: list[str] = []

    stores = load_master("stores")
    products = load_master("products")

    if stores is not None and not stores.empty:
        lines.append("【店舗マスタ情報】")
        lines.append(f"- 登録店舗数: {len(stores)}")
        sample_names = stores["name"].dropna().unique()[:10]
        lines.append("- 店舗名の例: " + ", ".join(map(str, sample_names)))
        lines.append("")

    if products is not None and not products.empty:
        lines.append("【商品マスタ情報】")
        lines.append(f"- 登録商品数: {len(products)}")
        sample_pnames = products["product_name"].dropna().unique()[:20]
        lines.append("- 商品名の例: " + ", ".join(map(str, sample_pnames)))
        lines.append("")

    return "\n".join(lines).strip()


# ========= 売上履歴（sales_history）の保存・読み込み =========
def save_sales_history(df: pd.DataFrame, batch_label: str, file_name: str) -> int:
    """
    売上データを sales_history テーブルに追記する。
    戻り値: 追加された行数
    """
    conn = get_conn()
    cur = conn.cursor()

    # テーブルのカラム情報を取得
    cur.execute("PRAGMA table_info(sales_history)")
    table_cols = [row[1] for row in cur.fetchall()]

    # 元CSVに存在する列
    base_cols = [
        "注文日時",
        "店舗コード",
        "店舗名",
        "商品明細(TOメニューID)",
        "商品名",
        "合計金額(税込)",
        "合計金額(税抜)",
    ]
    use_cols = [c for c in base_cols if c in df.columns]

    if not use_cols:
        conn.close()
        raise RuntimeError("売上履歴に保存できる列が見つかりません。列名を確認してください。")

    df_hist = df[use_cols].copy()

    # sales_historyのカラム名に合わせてリネーム
    rename_map = {
        "商品明細(TOメニューID)": "商品明細_TOメニューID",
        "合計金額(税込)": "合計金額税込",
        "合計金額(税抜)": "合計金額税抜",
    }
    df_hist.rename(columns=rename_map, inplace=True)

    # メタ情報追加
    df_hist["batch_label"] = batch_label
    df_hist["file_name"] = file_name
    df_hist["uploaded_at"] = datetime.now().isoformat(timespec="seconds")

    # テーブルに存在する列だけに絞る
    final_cols = [c for c in df_hist.columns if c in table_cols]
    df_hist = df_hist[final_cols]

    df_hist.to_sql("sales_history", conn, if_exists="append", index=False)
    added = len(df_hist)

    conn.commit()
    conn.close()
    return added


def load_sales_history() -> pd.DataFrame | None:
    """売上履歴を DataFrame として読み込む（まだ無ければ None）。"""
    conn = get_conn()
    try:
        df = pd.read_sql_query("SELECT * FROM sales_history", conn)
    except Exception:
        df = None
    conn.close()
    return df
