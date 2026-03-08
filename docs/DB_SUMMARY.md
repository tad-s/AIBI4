# 居酒屋 LLM BI アシスタント — DB構造・データサマリー

> 最終更新: 2026-03-09
> 対象プロジェクト: `C:\Users\tarchi\AIBI4`
> バックエンド: Supabase (PostgreSQL)

---

## 1. プロジェクト概要

テンアライド系居酒屋チェーンの POS データを Supabase に格納し、
LLM（GPT-4.1-mini）を活用した BI ダッシュボードアプリ（Streamlit）で分析する。

```
POS データ (Supabase)
    └─ visits / orders / order_items / stores / daily_weather
           ↓  get_izakaya_sales() RPC（DISTINCT ON 重複除去 + 天気 JOIN）
      Streamlit アプリ (app_v7_0.py)
           ↓  LLM チャット分析
        GPT-4.1-mini (OpenAI)
```

---

## 2. DB スキーマ

### 2-1. テーブル一覧

| テーブル | 種別 | 概要 |
|---|---|---|
| `stores` | 既存 + 拡張 | 店舗マスタ（住所・位置情報・天気地点を追加） |
| `visits` | 既存 | 来店記録（伝票単位）|
| `orders` | 既存 | 注文ヘッダ |
| `order_items` | 既存 | 注文明細（商品・数量・単価） |
| `weather_locations` | 新規 | 天気取得地点グリッド（0.01°≈1km 単位） |
| `daily_weather` | 新規 | 日別天気データ（Open-Meteo） |

---

### 2-2. stores テーブル

```sql
store_id        SERIAL PRIMARY KEY
store_name      TEXT
shop_code       TEXT
area_layer_name TEXT
address         TEXT              -- Google Maps Geocoding API で取得
latitude        DOUBLE PRECISION  -- 緯度
longitude       DOUBLE PRECISION  -- 経度
location_id     INTEGER           -- weather_locations への FK
```

| store_id | 店舗名 | 緯度/経度 | location_id | 備考 |
|---|---|---|---|---|
| 1 | SSOL幕張店 | なし | なし | 分析除外（ダミー） |
| 2 | 大ホール 渋谷レンガビル店 | 35.6582, 139.6994 | 5 | |
| 3 | 大ホール 八王子店 | 35.6664, 139.3160 | 6 | |
| 4 | 大ホール 池袋店 | 35.7348, 139.7077 | 17 | |
| 5 | テング酒場 お茶の水店 | 35.6997, 139.7624 | 15 | |
| 6 | テング酒場 神田南口店 | 35.6920, 139.7708 | 13 | |
| 7 | テンアライド本部 情報システム店 | なし | なし | 分析除外 |
| 8 | テンアライド 東神田研修センター店 | なし | なし | 分析除外 |
| 9 | テング酒場 神田東口店 | 35.6920, 139.7708 | 13 | 神田南口と同地点 |
| 10 | テング酒場 渋谷西口桜丘店 | 35.6560, 139.7016 | 5 | 渋谷エリアと同地点 |
| 11 | テング酒場 大宮そごう前店 | 35.9047, 139.6229 | 20 | |
| 12 | 大ホール 新宿東口靖国通り店 | 35.6915, 139.7012 | 12 | |
| 13 | テング酒場 松戸店 CKB有 | 35.7840, 139.9015 | 19 | |
| 14 | テング酒場 名古屋伏見店 | 35.1678, 136.8980 | 2 | |
| 15 | 道玄坂店 | 35.6582, 139.6982 | 5 | 渋谷エリアと同地点 |
| 16 | テング酒場 新宿郵便局前店 CKB有 | 35.6899, 139.6969 | 12 | 新宿エリアと同地点 |
| 17 | テング酒場 虎ノ門店 CKB無 | 35.6691, 139.7497 | 7 | |
| 18 | 横浜西口店 | 35.4675, 139.6215 | 4 | |
| 19 | 赤羽店 | 35.7800, 139.7231 | 18 | |
| 20 | テング酒場 銀座店 | 35.6682, 139.7592 | 8 | |
| 21 | テング酒場 東京八重洲口店 CKB無 | 35.6796, 139.7699 | 11 | |
| 22 | テング酒場 水道橋西口店 | 35.7019, 139.7519 | 14 | |
| 23 | テング酒場 歌舞伎座前東銀座店 | 35.6692, 139.7670 | 9 | |
| 24 | 本郷三丁目店 | 35.7047, 139.7616 | 15 | お茶の水と同地点 |
| 25 | 大ホール 上野浅草口店 | 35.7123, 139.7769 | 16 | |
| 26 | 麹町店 | 35.6844, 139.7377 | 10 | |
| 27 | テング酒場 新宿南口店 | 35.6888, 139.6986 | 12 | 新宿エリアと同地点 |
| 28 | 大ホール 川越クレアモール店 | 35.9090, 139.4824 | 21 | |
| 29 | テング酒場 名古屋松岡ビル店 | 35.1735, 136.8835 | 1 | |
| 30 | 大ホール 名古屋堀内ビル店 | 35.1824, 136.8767 | 3 | |

> **分析対象**: 15 店舗（実際に売上データが存在する店舗）

---

### 2-3. visits テーブル

```sql
visit_id        SERIAL PRIMARY KEY
store_id        INTEGER  REFERENCES stores(store_id)
receipt_no      TEXT
visit_time      TIMESTAMPTZ    -- 来店時刻（UTC 格納）
leave_time      TIMESTAMPTZ    -- 退店時刻
party_size      INTEGER        -- 人数
customer_layer  TEXT           -- 客層
```

**現在のデータ量（異常データ削除後）:**

| 項目 | 値 |
|---|---|
| 総レコード数 | 939 件（店舗×時間帯合計ベース） |
| データ期間 | 2024-09-01 〜 2025-10-31 |
| 対象月 | 2024-09 / 2024-10 / 2025-09 / 2025-10 |
| 対象店舗数 | 15 店舗 |

> ⚠️ 2026-02 の異常レコード（15件）は 2026-03-08 に削除済み

---

### 2-4. orders テーブル

```sql
order_id        SERIAL PRIMARY KEY
visit_id        INTEGER  REFERENCES visits(visit_id)
order_time      TIMESTAMPTZ
```

> ⚠️ **データ重複あり**: orders / order_items は visits 1件に対して平均数百件が紐付く状態（正常値は数件）。
> RPC 関数 `get_izakaya_sales()` 内の `DISTINCT ON` で重複除去済み。
> → `etc/supabase_setup.sql` を Supabase SQL Editor で実行することで適用。

---

### 2-5. order_items テーブル

```sql
item_id         SERIAL PRIMARY KEY
order_id        INTEGER  REFERENCES orders(order_id)
item_name_raw   TEXT     -- 商品名
quantity        INTEGER
unit_price      NUMERIC
line_type       TEXT     -- 'M': 商品明細（分析対象）, その他: 調整行など
```

---

### 2-6. weather_locations テーブル

```sql
location_id     SERIAL PRIMARY KEY
lat_grid        NUMERIC(7,4)   -- 緯度グリッド（小数第2位まで）
lon_grid        NUMERIC(7,4)   -- 経度グリッド
label           TEXT           -- 代表店舗名
UNIQUE (lat_grid, lon_grid)
```

**登録地点: 21 地点**

| location_id | lat_grid | lon_grid | 代表エリア | 共有店舗 |
|---|---|---|---|---|
| 1 | 35.17 | 136.88 | 名古屋（名駅） | 名古屋松岡ビル店 |
| 2 | 35.17 | 136.90 | 名古屋（伏見） | 名古屋伏見店 |
| 3 | 35.18 | 136.88 | 名古屋（西） | 名古屋堀内ビル店 |
| 4 | 35.47 | 139.62 | 横浜 | 横浜西口店 |
| 5 | 35.66 | 139.70 | 渋谷 | 渋谷レンガビル店・渋谷西口桜丘店・道玄坂店 |
| 6 | 35.67 | 139.32 | 八王子 | 八王子店 |
| 7 | 35.67 | 139.75 | 虎ノ門 | 虎ノ門店 |
| 8 | 35.67 | 139.76 | 銀座 | 銀座店 |
| 9 | 35.67 | 139.77 | 東銀座 | 歌舞伎座前東銀座店 |
| 10 | 35.68 | 139.74 | 麹町 | 麹町店 |
| 11 | 35.68 | 139.77 | 八重洲 | 東京八重洲口店 |
| 12 | 35.69 | 139.70 | 新宿 | 新宿東口店・新宿郵便局前店・新宿南口店 |
| 13 | 35.69 | 139.77 | 神田 | 神田南口店・神田東口店 |
| 14 | 35.70 | 139.75 | 水道橋 | 水道橋西口店 |
| 15 | 35.70 | 139.76 | お茶の水 | お茶の水店・本郷三丁目店 |
| 16 | 35.71 | 139.78 | 上野 | 上野浅草口店 |
| 17 | 35.73 | 139.71 | 池袋 | 池袋店 |
| 18 | 35.78 | 139.72 | 赤羽 | 赤羽店 |
| 19 | 35.78 | 139.90 | 松戸 | 松戸店 |
| 20 | 35.90 | 139.62 | 大宮 | 大宮そごう前店 |
| 21 | 35.91 | 139.48 | 川越 | 川越クレアモール店 |

---

### 2-7. daily_weather テーブル

```sql
location_id          INTEGER   NOT NULL  REFERENCES weather_locations(location_id)
date                 DATE      NOT NULL
temperature_2m_max   NUMERIC(5,2)   -- 最高気温 (℃)
temperature_2m_min   NUMERIC(5,2)   -- 最低気温 (℃)
temperature_2m_mean  NUMERIC(5,2)   -- 平均気温 (℃)
precipitation_sum    NUMERIC(6,2)   -- 降水量 (mm)
weathercode          SMALLINT       -- WMO 天気コード
weather_label        TEXT           -- 日本語天気ラベル
fetched_at           TIMESTAMPTZ    DEFAULT now()
PRIMARY KEY (location_id, date)
```

| 項目 | 値 |
|---|---|
| 地点数 | 21 地点 |
| 取得日数 | 426 日分（2024-09-01 〜 2025-10-31） |
| 総行数 | 8,946 行（21 × 426） |
| データソース | Open-Meteo Archive API（無料） |

---

### 2-8. テーブル関係図

```
stores ──────────────────────┐
  │ store_id                 │ location_id (FK)
  │                          ▼
visits ◄── store_id    weather_locations
  │ visit_id                 │ location_id
  ▼                          ▼
orders                  daily_weather
  │ order_id            (location_id + date) PK
  ▼
order_items
```

---

## 3. RPC 関数

### get_izakaya_sales(p_start_date, p_end_date, p_store_ids)

| 項目 | 内容 |
|---|---|
| 言語 | PL/pgSQL |
| セキュリティ | `SECURITY DEFINER`（RLS バイパス） |
| タイムアウト | `SET LOCAL statement_timeout = '0'` |
| 権限 | anon, authenticated ロールに EXECUTE 付与 |
| 重複除去 | `DISTINCT ON (visit_id, item_name_raw, quantity, unit_price)` |
| 天気結合 | `LEFT JOIN daily_weather` on `stores.location_id` + JST 日付 |

**返却カラム:**

| カラム名 | 型 | 日本語名 | 説明 |
|---|---|---|---|
| receipt_no | TEXT | 伝票番号 | |
| order_time | TIMESTAMPTZ | 注文日時 | |
| visit_time | TIMESTAMPTZ | 来店時間 | |
| leave_time | TIMESTAMPTZ | 退店時間 | |
| party_size | INTEGER | 人数 | |
| customer_layer | TEXT | 客層 | |
| store_name | TEXT | 店舗名 | |
| shop_code | TEXT | 店舗コード | |
| item_name_raw | TEXT | 商品名 | |
| quantity | INTEGER | 数量 | |
| unit_price | NUMERIC | 単価 | |
| temperature_2m_max | NUMERIC | — | 最高気温（天気なし → NULL） |
| temperature_2m_min | NUMERIC | — | 最低気温 |
| temperature_2m_mean | NUMERIC | — | 平均気温 |
| precipitation_sum | NUMERIC | — | 降水量 |
| weathercode | SMALLINT | — | WMO 天気コード |
| weather_label | TEXT | — | 日本語天気ラベル |

> 定義ファイル: `etc/supabase_setup.sql`（Supabase SQL Editor で実行）

---

## 4. 来店データ詳細サマリー（visits テーブル基準）

> データソース: Supabase visits テーブル（異常データ削除後）
> 集計基準: `receipt_no` の `nunique`（伝票数）

### 4-1. 店舗 × 月 伝票数

| 店舗名 | 2024-09 | 2024-10 | 2025-09 | 2025-10 | **合計** |
|---|---:|---:|---:|---:|---:|
| テング酒場 名古屋松岡ビル店 | 94 | 17 | 4 | 5 | **120** |
| テング酒場 神田南口店 | 81 | 16 | 0 | 1 | **98** |
| テング酒場 お茶の水店 | 84 | 1 | 3 | 0 | **88** |
| テング酒場 渋谷西口桜丘店 | 57 | 3 | 11 | 2 | **73** |
| テング酒場 東京八重洲口店 CKB無 | 61 | 7 | 4 | 0 | **72** |
| テング酒場 名古屋伏見店 | 34 | 3 | 34 | 1 | **72** |
| テング酒場 神田東口店 | 62 | 3 | 2 | 1 | **68** |
| テング酒場 歌舞伎座前東銀座店 | 46 | 9 | 2 | 0 | **57** |
| テング酒場 銀座店 | 35 | 15 | 5 | 1 | **56** |
| テング酒場 大宮そごう前店 | 42 | 6 | 7 | 0 | **55** |
| テング酒場 新宿南口店 | 19 | 18 | 2 | 4 | **43** |
| テング酒場 松戸店 CKB有 | 18 | 18 | 1 | 1 | **38** |
| テング酒場 新宿郵便局前店 CKB有 | 36 | 0 | 1 | 0 | **37** |
| テング酒場 虎ノ門店 CKB無 | 30 | 1 | 3 | 0 | **34** |
| テンアライド 東神田研修センター店 | 3 | 1 | 4 | 5 | **13** |
| **月計** | **702** | **118** | **83** | **21** | **924**（visits ベース） |

> 2024-09 が全体の 76% を占める。2024-10・2025-10 は月末のみの可能性あり。

---

### 4-2. 店舗 × 時間帯 伝票数（全月合計）

| 店舗名 | 〜17時(昼) | 17〜20時(夕方) | 20〜23時(夜) | 23時〜(深夜) | **合計** |
|---|---:|---:|---:|---:|---:|
| テング酒場 名古屋松岡ビル店 | 39 | 0 | 82 | 0 | **121** |
| テング酒場 神田南口店 | 51 | 0 | 47 | 0 | **98** |
| テング酒場 お茶の水店 | 22 | 0 | 67 | 0 | **89** |
| テング酒場 名古屋伏見店 | 8 | 0 | 65 | 0 | **73** |
| テング酒場 渋谷西口桜丘店 | 16 | 0 | 57 | 0 | **73** |
| テング酒場 東京八重洲口店 CKB無 | 4 | 0 | 67 | 1 | **72** |
| テング酒場 神田東口店 | 26 | 0 | 42 | 0 | **68** |
| テング酒場 歌舞伎座前東銀座店 | 18 | 0 | 38 | 1 | **57** |
| テング酒場 銀座店 | 55 | 0 | 1 | 0 | **56** |
| テング酒場 大宮そごう前店 | 16 | 0 | 39 | 0 | **55** |
| テング酒場 新宿南口店 | 46 | 0 | 0 | 5 | **51** |
| テング酒場 松戸店 CKB有 | 31 | 0 | 0 | 7 | **38** |
| テング酒場 新宿郵便局前店 CKB有 | 2 | 0 | 35 | 0 | **37** |
| テング酒場 虎ノ門店 CKB無 | 1 | 0 | 33 | 0 | **34** |
| テンアライド 東神田研修センター店 | 4 | 4 | 1 | 4 | **13** |
| SSOL幕張店 | 0 | 0 | 0 | 4 | **4** |
| **時間帯計** | **339** | **4** | **574** | **22** | **939** |
| **構成比** | **36.1%** | **0.4%** | **61.1%** | **2.3%** | — |

> **主要知見:**
> - 来店の 61% が 20〜23時（夜の居酒屋タイム）
> - 昼（〜17時）も 36% と多い（テスト・研修データ混在の可能性あり）
> - 17〜20時（夕方）はほぼゼロ（営業形態上の特性）
> - 深夜（23時〜）は松戸・新宿南口で多い

---

### 4-3. 月別サマリー

| 月 | 伝票数 | 売上明細行数(CSV)※ | 備考 |
|---|---:|---:|---|
| 2024-09 | 702 | 230,629 | 主力月（全体の 76%） |
| 2024-10 | 118 | 695 | 10月末のみの可能性 |
| 2025-09 | 83 | 44,077 | |
| 2025-10 | 21 | 7,582 | |
| **合計** | **924** | **282,983** | |

> ※ CSV 明細行数は orders/order_items の重複データを含む。
> 実際の明細数は RPC の `DISTINCT ON` 適用後の値を参照のこと。

---

## 5. データ品質メモ

### 5-1. orders / order_items の重複問題

| 項目 | 状況 |
|---|---|
| 問題 | orders / order_items テーブルに約 4〜5 倍の重複行が存在する |
| 原因 | インポートが複数回実行された可能性（visits には UNIQUE 制約あり） |
| 対処 | `get_izakaya_sales()` RPC で `DISTINCT ON` により DB レベルで除去 |
| 適用方法 | `etc/supabase_setup.sql` を Supabase SQL Editor で実行 |

### 5-2. visits の異常日付

| 項目 | 状況 |
|---|---|
| 問題 | visit_time が 2026-02 / 2026-10 の異常レコードが混入していた |
| 件数 | 約 15〜30 件（2026-03-08 に削除済み） |
| 対処（アプリ） | キャッシュ再生成時に「当月より未来の月」を自動除外する処理を追加 |
| 対処（DB） | `etc/cleanup_visits_anomaly.sql` Step 5 に CHECK 制約を用意 |

### 5-3. タイムゾーン

| テーブル/列 | 格納形式 | 表示変換 |
|---|---|---|
| visits.visit_time | UTC (TIMESTAMPTZ) | JST (Asia/Tokyo) に変換して表示 |
| orders.order_time | UTC | 同上 |
| daily_weather.date | DATE (JST 基準) | そのまま使用 |

---

## 6. ローカル CSV ファイル一覧

`data/` フォルダ内の主要ファイル:

| ファイル名 | サイズ | 行数 | 内容 |
|---|---|---|---|
| `sales_all_combined.csv` | 44.1 MB | 282,983 | 全月売上明細（結合済み、重複含む） |
| `sales_202409.csv` | 35.9 MB | 230,920 | 2024-09 月売上明細 |
| `sales_202509.csv` | 8.2 MB | 51,306 | 2025-09 月売上明細 |
| `sales_202410.csv` | 0.1 MB | 698 | 2024-10 月売上明細 |
| `sales_202510.csv` | 0.07 MB | 442 | 2025-10 月売上明細 |
| `daily_weather.csv` | 492 KB | 8,946 | 日別天気データ（全地点） |
| `summary_cache.json` | — | — | 店舗×月・店舗×時間帯の事前集計キャッシュ |

---

## 7. SQL スクリプト一覧

`etc/` フォルダ内:

| ファイル | 実行目的 | 実行タイミング |
|---|---|---|
| `supabase_setup.sql` | インデックス・タイムアウト設定・RPC 最終版（天気 JOIN + 重複除去）| **毎回の初期セットアップ / RPC 更新時** |
| `add_location_columns.sql` | stores テーブルへの位置情報カラム追加 | 位置情報拡張時（初回のみ） |
| `create_daily_weather.sql` | 天気テーブル作成・権限設定 | 天気機能追加時（初回のみ） |
| `cleanup_visits_anomaly.sql` | 異常日付 visits レコードの調査・削除 | 異常データ発生時 |
| `fix_duplicate_rpc.sql` | （旧版） supabase_setup.sql の前身 | 参照用のみ |

---

## 8. Python スクリプト一覧

| ファイル | 役割 |
|---|---|
| `supabase_loader.py` | Supabase クライアント・データ取得共通モジュール |
| `build_summary_cache.py` | visits テーブルから summary_cache.json を生成するバッチ |
| `fetch_all_data.py` | 全月売上データを Supabase から取得・CSV 保存 |
| `fetch_weather_for_stores.py` | 店舗位置情報 → Open-Meteo → daily_weather テーブル登録 |
| `geocode_stores.py` | 店舗名 → Google Maps API → 住所・緯度経度取得 → Supabase 登録 |
| `app_v7_0.py` | Streamlit BI アプリ（最新版） |

---

## 9. アプリ主要仕様（app_v7_0.py）

| 機能 | 仕様 |
|---|---|
| データ取得 | Supabase RPC（CHUNK_DAYS=30 日チャンク、ページネーション対応） |
| 天気データ | 取得時に自動付与（daily_weather LEFT JOIN） |
| サマリーキャッシュ | visits テーブルから事前集計、JSON 保存、ヒートマップ表示 |
| LLM | GPT-4.1-mini、matplotlib グラフ生成コードを `exec()` |
| グラフ品質 | 金額列に「（円）」ラベル・カンマ区切り強制、空データガード |
| 異常データ防止 | キャッシュ再生成時に未来月を自動除外・警告表示 |

---

*このドキュメントは `docs/DB_SUMMARY.md` に保存されています。*
