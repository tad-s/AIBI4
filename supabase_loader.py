"""
supabase_loader.py
Supabase から居酒屋売上データを取得して分析用 pandas DataFrame に変換するモジュール。

【取得方式】
  Supabase RPC 関数 get_izakaya_sales() を「週単位チャンク」で呼び出す。
  1 回の SQL が処理する日付範囲を 7 日以内に絞ることで
  Supabase free tier のステートメントタイムアウトを回避する。

  ★ 初回セットアップ: etc/supabase_setup.sql を Supabase SQL Editor で実行してください。

テーブル構成:
  stores       → 店舗マスタ
  visits       → 来店・伝票（1来店=1レコード）
  orders       → 注文送信履歴（1伝票に複数注文）
  order_items  → 注文明細（1注文に複数商品）
"""

import os
import calendar
from datetime import date, timedelta

import pandas as pd
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://yixsaqvjekygmnthgvaq.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

# 1 回の RPC 呼び出しがカバーする日数（短いほどタイムアウトしにくい）
CHUNK_DAYS = 7   # 週単位で分割（2024-09 など大量月のタイムアウト対策）

# PostgREST のデフォルト最大行数（超過すると自動的に打ち切られる）
# .range() を使ってページネーションを行い全件取得する
RPC_PAGE_SIZE = 1000

# RPC 関数が未作成の場合に表示するメッセージ
RPC_SETUP_MSG = (
    "Supabase SQL Editor で etc/supabase_setup.sql を実行してください。\n"
    "（get_izakaya_sales 関数が存在しないか、実行権限がありません）"
)


def _week_ranges(start_date: str, end_date: str) -> list[tuple[str, str]]:
    """日付範囲を CHUNK_DAYS 日ごとのチャンクに分割する。"""
    start = date.fromisoformat(start_date)
    end   = date.fromisoformat(end_date)
    chunks = []
    cur = start
    while cur <= end:
        chunk_end = min(cur + timedelta(days=CHUNK_DAYS - 1), end)
        chunks.append((cur.isoformat(), chunk_end.isoformat()))
        cur = chunk_end + timedelta(days=1)
    return chunks


def get_client() -> Client:
    """Supabase クライアントを生成して返す。"""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError(
            "SUPABASE_URL または SUPABASE_KEY が設定されていません。"
            ".env ファイルを確認してください。"
        )
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ──────────────────────────────────────────────
# 公開 API
# ──────────────────────────────────────────────

def fetch_stores(client: Client) -> pd.DataFrame:
    """店舗一覧 DataFrame を返す（store_id, store_name, shop_code, area_layer_name）。"""
    result = client.table("stores").select(
        "store_id, store_name, shop_code, area_layer_name"
    ).execute()
    return pd.DataFrame(result.data or [])


def fetch_visits_for_summary(client: Client) -> pd.DataFrame:
    """
    サマリーキャッシュ用に visits + stores を全件取得して DataFrame を返す。
    visits テーブルは小さい（～数千行）のでページネーションで完全取得する。

    返却列: store_name, receipt_no, visit_time (UTC TIMESTAMPTZ 文字列)
    """
    # ① stores を全件取得（～30件なので1回で完了）
    stores_res = client.table("stores").select("store_id,store_name").execute()
    stores_df  = pd.DataFrame(stores_res.data or [])
    if stores_df.empty:
        return pd.DataFrame()
    store_map: dict[int, str] = dict(
        zip(stores_df["store_id"], stores_df["store_name"])
    )

    # ② visits を全件ページネーション取得
    PAGE = 1000
    all_rows: list[dict] = []
    offset = 0
    while True:
        res = (
            client.table("visits")
            .select("store_id,receipt_no,visit_time")
            .not_.is_("visit_time", "null")
            .range(offset, offset + PAGE - 1)
            .execute()
        )
        rows = res.data or []
        all_rows.extend(rows)
        if len(rows) < PAGE:
            break
        offset += PAGE

    if not all_rows:
        return pd.DataFrame()

    df = pd.DataFrame(all_rows)
    df["store_name"] = df["store_id"].map(store_map)
    df = df.dropna(subset=["store_name"])
    return df[["store_name", "receipt_no", "visit_time"]]


def fetch_available_months(client: Client) -> list[str]:
    """
    visits テーブルから来店データが存在する月（YYYY-MM 形式）の一覧を返す。
    RLS が有効でデータが読めない場合は空リストを返す。
    """
    try:
        result = (
            client.table("visits")
            .select("visit_time")
            .not_.is_("visit_time", "null")
            .limit(3000)
            .execute()
        )
        if not result.data:
            return []
        dates = pd.to_datetime(
            [r["visit_time"] for r in result.data], errors="coerce", utc=True
        )
        return sorted({d.strftime("%Y-%m") for d in dates if pd.notna(d)})
    except Exception:
        return []


def fetch_sales_data(
    client: Client,
    start_date: str,                    # "YYYY-MM-DD"
    end_date: str,                      # "YYYY-MM-DD"
    store_ids: list[int] | None = None,
    progress_callback=None,             # callback(fetched_rows: int) or None
) -> pd.DataFrame:
    """
    指定期間の売上データを Supabase RPC 関数経由で取得し、分析用 DataFrame を返す。

    【仕組み】
      get_izakaya_sales() RPC 関数を CHUNK_DAYS 日ごとに分割して呼び出す。
      1 回の SQL が処理する行数を削減しタイムアウトを防ぐ。

      事前準備: etc/supabase_setup.sql を Supabase SQL Editor で実行してください。

    返却 DataFrame の主な列:
        伝票番号, 注文日時, 来店時間, 退店時間,
        店舗名, 店舗コード, 商品名, 数量, 単価,
        合計金額(税込), 人数, 客層

    RPC 関数が存在しない場合は RuntimeError を送出する。
    """
    chunks = _week_ranges(start_date, end_date)
    all_rows: list[dict] = []

    for chunk_start, chunk_end in chunks:
        params: dict = {
            "p_start_date": chunk_start,
            "p_end_date":   chunk_end,
        }
        if store_ids is not None:
            params["p_store_ids"] = store_ids

        # PostgREST のデフォルト 1000 行上限を回避するためページネーションで全件取得
        offset = 0
        while True:
            try:
                result = (
                    client.rpc("get_izakaya_sales", params)
                    .range(offset, offset + RPC_PAGE_SIZE - 1)
                    .execute()
                )
            except Exception as e:
                err_str = str(e)
                if (
                    "get_izakaya_sales" in err_str
                    or "Could not find" in err_str
                    or "42883" in err_str
                ):
                    raise RuntimeError(RPC_SETUP_MSG) from e
                raise

            rows = result.data or []
            all_rows.extend(rows)

            if len(rows) < RPC_PAGE_SIZE:
                break  # これ以上データなし
            offset += RPC_PAGE_SIZE

        if progress_callback:
            progress_callback(len(all_rows))

    if not all_rows:
        return pd.DataFrame()

    df = pd.DataFrame(all_rows)

    # 数値変換
    df["unit_price"] = pd.to_numeric(df["unit_price"], errors="coerce").fillna(0)
    df["quantity"]   = pd.to_numeric(df["quantity"],   errors="coerce").fillna(0)
    if "party_size" in df.columns:
        df["party_size"] = (
            pd.to_numeric(df["party_size"], errors="coerce").fillna(0).astype(int)
        )

    # 日時変換（UTC → JST）
    for col in ["visit_time", "leave_time", "order_time"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)
            try:
                df[col] = df[col].dt.tz_convert("Asia/Tokyo")
            except Exception:
                pass

    # 伝票単位の合計金額（unit_price × quantity の合計）
    df["_line_total"] = df["unit_price"] * df["quantity"]
    visit_total = (
        df.groupby("receipt_no")["_line_total"]
        .sum()
        .rename("合計金額(税込)")
    )
    df = df.join(visit_total, on="receipt_no")

    # カラム名を日本語にリネーム
    df = df.rename(columns={
        "receipt_no":     "伝票番号",
        "order_time":     "注文日時",
        "visit_time":     "来店時間",
        "leave_time":     "退店時間",
        "party_size":     "人数",
        "customer_layer": "客層",
        "store_name":     "店舗名",
        "shop_code":      "店舗コード",
        "item_name_raw":  "商品名",
        "quantity":       "数量",
        "unit_price":     "単価",
    })

    df = df.drop(columns=["_line_total"], errors="ignore")

    return df.reset_index(drop=True)


def fetch_daily_weather_by_store(
    client: Client,
    start_date: str,  # "YYYY-MM-DD"
    end_date: str,    # "YYYY-MM-DD"
) -> pd.DataFrame:
    """
    Supabase の daily_weather テーブルから全店舗の天気データを取得する。
    stores.location_id を経由して店舗名と紐付ける。

    返却列: store_name, date (datetime64, naive),
            temperature_2m_max, temperature_2m_min, temperature_2m_mean,
            precipitation_sum, weathercode, weather_label
    """
    # ① stores テーブルから store_name + location_id を取得
    stores_res = client.table("stores").select("store_name,location_id").execute()
    stores_df = pd.DataFrame(stores_res.data or [])
    if stores_df.empty or "location_id" not in stores_df.columns:
        return pd.DataFrame()

    stores_loc = stores_df.dropna(subset=["location_id"])
    valid_loc_ids = stores_loc["location_id"].astype(int).tolist()
    if not valid_loc_ids:
        return pd.DataFrame()

    # ② daily_weather をページネーションで全件取得
    PAGE = 1000
    all_rows: list[dict] = []
    offset = 0
    while True:
        res = (
            client.table("daily_weather")
            .select(
                "location_id,date,"
                "temperature_2m_max,temperature_2m_min,temperature_2m_mean,"
                "precipitation_sum,weathercode,weather_label"
            )
            .in_("location_id", valid_loc_ids)
            .gte("date", start_date)
            .lte("date", end_date)
            .range(offset, offset + PAGE - 1)
            .execute()
        )
        rows = res.data or []
        all_rows.extend(rows)
        if len(rows) < PAGE:
            break
        offset += PAGE

    if not all_rows:
        return pd.DataFrame()

    df_w = pd.DataFrame(all_rows)
    df_w["date"] = pd.to_datetime(df_w["date"]).dt.normalize()

    # ③ location_id → store_name を JOIN（1 地点が複数店舗に対応）
    stores_loc = stores_loc.copy()
    stores_loc["location_id"] = stores_loc["location_id"].astype(int)
    df_w["location_id"] = df_w["location_id"].astype(int)
    df_out = df_w.merge(stores_loc[["store_name", "location_id"]], on="location_id", how="left")
    df_out = df_out.drop(columns=["location_id"])

    return df_out.reset_index(drop=True)


def months_to_date_range(months: list[str]) -> tuple[str, str]:
    """
    ['2024-09', '2024-10'] → ('2024-09-01', '2024-10-31')
    """
    if not months:
        raise ValueError("月が指定されていません。")
    starts, ends = [], []
    for m in months:
        y, mo = int(m.split("-")[0]), int(m.split("-")[1])
        starts.append(f"{y}-{mo:02d}-01")
        last_day = calendar.monthrange(y, mo)[1]
        ends.append(f"{y}-{mo:02d}-{last_day:02d}")
    return min(starts), max(ends)
