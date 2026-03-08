"""
geocode_stores.py
stores テーブルの各店舗に住所・緯度・経度を付与して Supabase に登録する。

事前準備:
  1. Supabase SQL Editor で etc/add_location_columns.sql を実行
  2. .env に GOOGLE_MAPS_API_KEY=xxx を追加
  3. python geocode_stores.py
"""

import io
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import os
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))
from supabase_loader import get_client, fetch_stores

GOOGLE_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"

# 店舗名から住所検索する際の付加キーワード（精度向上）
SEARCH_SUFFIX = " 居酒屋 日本"


def geocode(query: str) -> dict | None:
    """
    Google Maps Geocoding API で住所と緯度経度を取得する。
    Returns: {"address": str, "lat": float, "lng": float} or None
    """
    params = {
        "address": query,
        "key": GOOGLE_API_KEY,
        "language": "ja",
        "region": "JP",
    }
    try:
        resp = requests.get(GEOCODE_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "OK" or not data.get("results"):
            return None
        result = data["results"][0]
        address = result.get("formatted_address", "")
        loc = result["geometry"]["location"]
        return {"address": address, "lat": loc["lat"], "lng": loc["lng"]}
    except Exception as e:
        print(f"    Geocoding エラー: {e}")
        return None


def update_store(sb, store_id: int, address: str, lat: float, lng: float) -> bool:
    """Supabase の stores テーブルを 1 件更新する。"""
    try:
        sb.table("stores").update({
            "address": address,
            "latitude": lat,
            "longitude": lng,
        }).eq("store_id", store_id).execute()
        return True
    except Exception as e:
        print(f"    Supabase 更新エラー: {e}")
        return False


def main():
    print("=" * 60)
    print("stores テーブル 住所・位置情報 登録スクリプト")
    print("=" * 60)

    if not GOOGLE_API_KEY:
        print("❌ GOOGLE_MAPS_API_KEY が .env に設定されていません。")
        print("   .env に以下を追加してください:")
        print("   GOOGLE_MAPS_API_KEY=あなたのAPIキー")
        sys.exit(1)

    print(f"\n✅ Google Maps API キー確認済み")

    # Supabase 接続
    print("\n[1] Supabase に接続中...")
    try:
        sb = get_client()
        df_stores = fetch_stores(sb)
        print(f"    ✅ {len(df_stores)} 店舗を取得")
    except Exception as e:
        print(f"    ❌ 接続失敗: {e}")
        sys.exit(1)

    # 対象店舗（ダミー・本部系を除外）
    skip_keywords = ["SSOL", "本部", "研修センター", "情報システム"]
    df_target = df_stores[
        ~df_stores["store_name"].apply(
            lambda n: any(kw in str(n) for kw in skip_keywords)
        )
    ].copy()
    print(f"    対象: {len(df_target)} 店舗（ダミー・本部系 {len(df_stores)-len(df_target)} 件を除外）")

    print(f"\n[2] 住所・位置情報を取得して登録中...")
    results = []
    success_count = 0
    fail_count = 0

    for _, row in df_target.iterrows():
        store_id   = row["store_id"]
        store_name = row["store_name"]

        # 店舗名の整形（不要な記号・注記を除去して検索精度向上）
        clean_name = (
            store_name
            .replace("　CKB有", "").replace("　CKＢ有", "")
            .replace("　CKB無", "").replace("　CKＢ無", "")
            .strip()
        )
        search_query = clean_name + SEARCH_SUFFIX

        print(f"  [{store_id:2d}] {store_name}")
        print(f"        検索: {search_query}")

        geo = geocode(search_query)

        if geo:
            print(f"        住所: {geo['address']}")
            print(f"        座標: ({geo['lat']:.6f}, {geo['lng']:.6f})")
            ok = update_store(sb, store_id, geo["address"], geo["lat"], geo["lng"])
            if ok:
                print(f"        ✅ Supabase 登録完了")
                success_count += 1
                results.append({
                    "store_id": store_id,
                    "store_name": store_name,
                    "address": geo["address"],
                    "latitude": geo["lat"],
                    "longitude": geo["lng"],
                    "status": "OK",
                })
            else:
                fail_count += 1
                results.append({
                    "store_id": store_id,
                    "store_name": store_name,
                    "address": geo["address"],
                    "latitude": geo["lat"],
                    "longitude": geo["lng"],
                    "status": "DB_ERROR",
                })
        else:
            print(f"        ⚠️  住所取得失敗（手動設定が必要）")
            fail_count += 1
            results.append({
                "store_id": store_id,
                "store_name": store_name,
                "address": None,
                "latitude": None,
                "longitude": None,
                "status": "GEOCODE_FAIL",
            })

        # Google Maps API のレートリミット対策（1秒待機）
        time.sleep(1.0)

    # 結果を CSV に保存
    df_result = pd.DataFrame(results)
    out = Path("data") / "stores_with_location.csv"
    df_result.to_csv(out, index=False, encoding="utf-8-sig")

    # サマリー
    print(f"\n{'='*60}")
    print("完了サマリー")
    print(f"{'='*60}")
    print(f"  成功: {success_count} 件")
    print(f"  失敗: {fail_count} 件")
    print(f"  結果CSV: {out}")

    if fail_count > 0:
        failed = df_result[df_result["status"] != "OK"]
        print(f"\n⚠️  要確認（手動登録が必要な店舗）:")
        for _, r in failed.iterrows():
            print(f"  store_id={r['store_id']}: {r['store_name']} [{r['status']}]")

    # stores_master.csv も更新
    df_master = pd.read_csv("data/stores_master.csv", encoding="utf-8-sig")
    df_master = df_master.merge(
        df_result[["store_id", "address", "latitude", "longitude"]],
        on="store_id", how="left"
    )
    df_master.to_csv("data/stores_master.csv", index=False, encoding="utf-8-sig")
    print(f"\n✅ data/stores_master.csv も更新しました")


if __name__ == "__main__":
    main()
