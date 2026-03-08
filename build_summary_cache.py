"""
build_summary_cache.py
Supabase の visits テーブルから店舗×月・店舗×時間帯の伝票数を集計し
data/summary_cache.json に保存する。

使い方:
    python build_summary_cache.py

定期実行例 (週次):
    Windowsタスクスケジューラ / cron で毎週月曜朝に実行する。

出力:
    data/summary_cache.json
        {
          "generated_at": "2025-03-07 12:00:00",
          "data_source": "supabase",
          "store_month": [
            {"店舗名": "...", "month": "2024-09", "伝票数": 123},
            ...
          ],
          "store_timeband": [
            {"店舗名": "...", "time_band": "17〜20時(夕方)", "伝票数": 456},
            ...
          ]
        }

注意:
    ここで集計するのは visits テーブルの「来店記録がある伝票数」です。
    注文明細（order_items）が紐づいていない来店を含む場合があります。
    LLM 分析に使うデータは get_izakaya_sales RPC の結果と一致します。
"""

import io
import sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import json
from datetime import datetime
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path(__file__).resolve().parent / "data"
OUTPUT_FILE = DATA_DIR / "summary_cache.json"

# 時間帯ラベル（左閉・右開）
TIME_BANDS = [
    (0,  17, "〜17時(昼)"),
    (17, 20, "17〜20時(夕方)"),
    (20, 23, "20〜23時(夜)"),
    (23, 24, "23時〜(深夜)"),
]
TIMEBAND_ORDER = [b[2] for b in TIME_BANDS]


def hour_to_band(h: int) -> str:
    for lo, hi, label in TIME_BANDS:
        if lo <= h < hi:
            return label
    return "23時〜(深夜)"


def build_cache_from_supabase() -> dict:
    """Supabase の visits テーブルを全件取得してサマリーを構築する。"""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from supabase_loader import get_client, fetch_visits_for_summary

    print("  Supabase に接続中...")
    try:
        sb = get_client()
        print("  ✅ 接続成功")
    except Exception as e:
        print(f"  ❌ 接続失敗: {e}")
        return {}

    print("  visits テーブルを取得中...")
    df = fetch_visits_for_summary(sb)
    if df.empty:
        print("  ⚠️  visits データが空です。")
        return {}

    print(f"  取得: {len(df):,} 件の来店記録")

    # ── 来店時間を JST に変換 ──────────────────────────────────────────
    dt = pd.to_datetime(df["visit_time"], format="ISO8601", errors="coerce", utc=True)
    jst = dt.dt.tz_convert("Asia/Tokyo")
    df["month"]     = jst.dt.strftime("%Y-%m")
    df["hour"]      = jst.dt.hour
    df["time_band"] = df["hour"].apply(hour_to_band)
    df = df.dropna(subset=["month"])

    # ── 店舗×月 集計 ─────────────────────────────────────────────────
    store_month = (
        df.groupby(["store_name", "month"], sort=True)["receipt_no"]
        .nunique()
        .reset_index()
        .rename(columns={"store_name": "店舗名", "receipt_no": "伝票数"})
    )

    # ── 店舗×時間帯 集計（全月合算）──────────────────────────────────
    df["time_band"] = pd.Categorical(
        df["time_band"], categories=TIMEBAND_ORDER, ordered=True
    )
    store_timeband = (
        df.groupby(["store_name", "time_band"], sort=True, observed=True)["receipt_no"]
        .nunique()
        .reset_index()
        .rename(columns={"store_name": "店舗名", "receipt_no": "伝票数"})
    )

    return {
        "generated_at":   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data_source":    "supabase",
        "total_visits":   int(len(df)),
        "store_month":    store_month.to_dict(orient="records"),
        "store_timeband": store_timeband.to_dict(orient="records"),
    }


def main():
    print("=" * 60)
    print("データサマリーキャッシュ生成スクリプト（Supabase版）")
    print("=" * 60)

    cache = build_cache_from_supabase()
    if not cache:
        print("❌ キャッシュ生成に失敗しました。")
        sys.exit(1)

    OUTPUT_FILE.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    n_sm = len(cache["store_month"])
    n_st = len(cache["store_timeband"])
    print(f"\n✅ 保存完了: {OUTPUT_FILE}")
    print(f"   店舗×月 集計行数   : {n_sm:,}")
    print(f"   店舗×時間帯 集計行数: {n_st:,}")
    print(f"   生成日時           : {cache['generated_at']}")
    print(f"   データソース       : {cache['data_source']}")


if __name__ == "__main__":
    main()
