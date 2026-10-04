# Supabase DB 構造まとめ — izakaya データセット

> 作成日: 2026-06-23  
> 対象: テング酒場 / 大ホール（テンアライド系居酒屋チェーン）  
> 定義ファイル: `etc/supabase_setup.sql`、`etc/v8_migration.sql`

---

## 1. 全体像

```
【Supabase (PostgreSQL)】

  stores ────────────────── location_id ──► weather_locations
    │ store_id                                      │ location_id
    │                                               ▼
  visits ◄── store_id                         daily_weather
    │ visit_id                              (location_id + date) PK
    ▼
  orders ◄── visit_id
    │ order_id
    ▼
  order_items ◄── order_id
  （line_type='M' のみ分析対象）

  monthly_summary ◄── store_id  ← refresh_monthly_summary() で再計算
  （月次集計キャッシュ）


【RPC 関数】
  get_izakaya_sales()         売上明細取得（天気 JOIN + 重複除去）
  get_available_months()      利用可能な月一覧
  refresh_monthly_summary()   月次集計の再計算・保存
  get_monthly_summary()       月次集計の軽量取得
  get_basket_pairs()          バスケット分析（共起ペア）
```

---

## 2. テーブル詳細

### 2-1. stores（店舗マスタ）

| カラム名 | 型 | 説明 |
|---|---|---|
| store_id | SERIAL PK | 店舗 ID |
| store_name | TEXT | 店舗名 |
| shop_code | TEXT | 店舗コード |
| area_layer_name | TEXT | エリア区分名 |
| address | TEXT | 住所（Google Maps Geocoding API で取得） |
| latitude | DOUBLE PRECISION | 緯度 |
| longitude | DOUBLE PRECISION | 経度 |
| location_id | INTEGER FK | 天気取得地点（→ weather_locations） |

**登録店舗一覧（30 件）**

| store_id | 店舗名 | location_id | 備考 |
|---|---|---|---|
| 1 | SSOL幕張店 | — | 分析除外（ダミー） |
| 2 | 大ホール 渋谷レンガビル店 | 5（渋谷） | |
| 3 | 大ホール 八王子店 | 6（八王子） | |
| 4 | 大ホール 池袋店 | 17（池袋） | |
| 5 | テング酒場 お茶の水店 | 15（お茶の水） | |
| 6 | テング酒場 神田南口店 | 13（神田） | |
| 7 | テンアライド本部 情報システム店 | — | 分析除外 |
| 8 | テンアライド 東神田研修センター店 | — | 分析除外 |
| 9 | テング酒場 神田東口店 | 13（神田） | 神田南口と同地点 |
| 10 | テング酒場 渋谷西口桜丘店 | 5（渋谷） | 渋谷レンガビル店と同地点 |
| 11 | テング酒場 大宮そごう前店 | 20（大宮） | |
| 12 | 大ホール 新宿東口靖国通り店 | 12（新宿） | |
| 13 | テング酒場 松戸店 CKB有 | 19（松戸） | |
| 14 | テング酒場 名古屋伏見店 | 2（名古屋伏見） | |
| 15 | 道玄坂店 | 5（渋谷） | 渋谷グループと同地点 |
| 16 | テング酒場 新宿郵便局前店 CKB有 | 12（新宿） | 新宿エリアと同地点 |
| 17 | テング酒場 虎ノ門店 CKB無 | 7（虎ノ門） | |
| 18 | 横浜西口店 | 4（横浜） | |
| 19 | 赤羽店 | 18（赤羽） | |
| 20 | テング酒場 銀座店 | 8（銀座） | |
| 21 | テング酒場 東京八重洲口店 CKB無 | 11（八重洲） | |
| 22 | テング酒場 水道橋西口店 | 14（水道橋） | |
| 23 | テング酒場 歌舞伎座前東銀座店 | 9（東銀座） | |
| 24 | 本郷三丁目店 | 15（お茶の水） | お茶の水店と同地点 |
| 25 | 大ホール 上野浅草口店 | 16（上野） | |
| 26 | 麹町店 | 10（麹町） | |
| 27 | テング酒場 新宿南口店 | 12（新宿） | 新宿エリアと同地点 |
| 28 | 大ホール 川越クレアモール店 | 21（川越） | |
| 29 | テング酒場 名古屋松岡ビル店 | 1（名古屋名駅） | |
| 30 | 大ホール 名古屋堀内ビル店 | 3（名古屋西） | |

> 分析対象（売上データあり）: **15 店舗**（store_id 2, 4, 5, 6, 9, 10, 11, 12, 13, 14, 16, 17, 20, 22, 23 など）

---

### 2-2. visits（来店記録）

| カラム名 | 型 | 説明 |
|---|---|---|
| visit_id | SERIAL PK | 来店 ID |
| store_id | INTEGER FK | 店舗 ID（→ stores） |
| receipt_no | TEXT | 伝票番号 ※店舗・日付をまたいで重複あり |
| visit_time | TIMESTAMPTZ | 来店時刻（**UTC** 格納、JST = UTC+9） |
| leave_time | TIMESTAMPTZ | 退店時刻（UTC） |
| party_size | INTEGER | 来店人数 |
| customer_layer | TEXT | 客層 |

**インデックス:**

```sql
idx_visits_visit_time          ON visits(visit_time)
idx_visits_store_time          ON visits(store_id, visit_time)   -- V8追加
idx_visits_yyyymm              ON visits(date_trunc('month', visit_time AT TIME ZONE 'Asia/Tokyo'))
```

**データ量サマリー:**

| 月 | 伝票数 | 構成比 |
|---|---:|---|
| 2024-09 | 702 | 76% |
| 2024-10 | 118 | 13% |
| 2025-09 | 83 | 9% |
| 2025-10 | 21 | 2% |
| **合計** | **924** | — |

> ⚠️ 総件数は 939 件だが、伝票ベースの合計は 924（SSOL幕張店などの除外分を含む）。  
> ⚠️ 2026-02 / 2026-10 の異常日付レコード（15件）は 2026-03-08 に削除済み。

**店舗 × 月 伝票数:**

| 店舗名 | 2024-09 | 2024-10 | 2025-09 | 2025-10 | 合計 |
|---|---:|---:|---:|---:|---:|
| テング酒場 名古屋松岡ビル店 | 94 | 17 | 4 | 5 | **120** |
| テング酒場 神田南口店 | 81 | 16 | 0 | 1 | **98** |
| テング酒場 お茶の水店 | 84 | 1 | 3 | 0 | **88** |
| テング酒場 渋谷西口桜丘店 | 57 | 3 | 11 | 2 | **73** |
| テング酒場 東京八重洲口店 | 61 | 7 | 4 | 0 | **72** |
| テング酒場 名古屋伏見店 | 34 | 3 | 34 | 1 | **72** |
| テング酒場 神田東口店 | 62 | 3 | 2 | 1 | **68** |
| テング酒場 歌舞伎座前東銀座店 | 46 | 9 | 2 | 0 | **57** |
| テング酒場 銀座店 | 35 | 15 | 5 | 1 | **56** |
| テング酒場 大宮そごう前店 | 42 | 6 | 7 | 0 | **55** |
| テング酒場 新宿南口店 | 19 | 18 | 2 | 4 | **43** |
| テング酒場 松戸店 CKB有 | 18 | 18 | 1 | 1 | **38** |
| テング酒場 新宿郵便局前店 | 36 | 0 | 1 | 0 | **37** |
| テング酒場 虎ノ門店 | 30 | 1 | 3 | 0 | **34** |
| テンアライド 東神田研修センター店 | 3 | 1 | 4 | 5 | **13** |

**来店時間帯分布（全月合計）:**

| 時間帯 | 件数 | 構成比 |
|---|---:|---|
| 〜17時（昼） | 339 | 36.1% |
| 17〜20時（夕方） | 4 | 0.4% |
| 20〜23時（夜） | 574 | 61.1% |
| 23時〜（深夜） | 22 | 2.3% |

---

### 2-3. orders（注文ヘッダ）

| カラム名 | 型 | 説明 |
|---|---|---|
| order_id | SERIAL PK | 注文 ID |
| visit_id | INTEGER FK | 来店 ID（→ visits） |
| order_time | TIMESTAMPTZ | 注文時刻（UTC） |

**インデックス:**

```sql
idx_orders_visit_id   ON orders(visit_id)
```

> ⚠️ **重複問題**: 同一 visit_id に対して本来 1〜数件のはずが、数百件の orders が紐付く場合がある（複数回インポートによる重複の可能性）。RPC の `DISTINCT ON` で除去。

---

### 2-4. order_items（注文明細）

| カラム名 | 型 | 説明 |
|---|---|---|
| item_id | SERIAL PK | 明細 ID |
| order_id | INTEGER FK | 注文 ID（→ orders） |
| item_name_raw | TEXT | 商品名（生データ） |
| quantity | INTEGER | 数量 |
| unit_price | NUMERIC | 単価（円） |
| line_type | TEXT | 行種別：`'M'` = 商品明細（分析対象）、その他 = 調整行 |

**インデックス:**

```sql
idx_order_items_order_id     ON order_items(order_id)
idx_order_items_line_type    ON order_items(line_type)
idx_order_items_type_order   ON order_items(line_type, order_id) WHERE line_type = 'M'  -- V8追加
idx_order_items_itemname     ON order_items(item_name_raw) WHERE line_type = 'M'        -- V8追加
```

**データ量:** 約 282,983 行（重複含む）。`DISTINCT ON` 適用後の実質明細数は概算で約 56,000 行程度。

---

### 2-5. weather_locations（天気取得地点）

| カラム名 | 型 | 説明 |
|---|---|---|
| location_id | SERIAL PK | 地点 ID |
| lat_grid | NUMERIC(7,4) | 緯度グリッド（小数第2位まで丸め） |
| lon_grid | NUMERIC(7,4) | 経度グリッド（同上） |
| label | TEXT | 代表エリア名 |
| — | UNIQUE | (lat_grid, lon_grid) |

**izakaya 使用地点（21地点）:**

| location_id | エリア | lat / lon | 対象店舗 |
|---|---|---|---|
| 1 | 名古屋（名駅） | 35.17 / 136.88 | 名古屋松岡ビル店 |
| 2 | 名古屋（伏見） | 35.17 / 136.90 | 名古屋伏見店 |
| 3 | 名古屋（西） | 35.18 / 136.88 | 名古屋堀内ビル店 |
| 4 | 横浜 | 35.47 / 139.62 | 横浜西口店 |
| 5 | 渋谷 | 35.66 / 139.70 | 渋谷レンガビル店・渋谷西口桜丘店・道玄坂店 |
| 6 | 八王子 | 35.67 / 139.32 | 八王子店 |
| 7 | 虎ノ門 | 35.67 / 139.75 | 虎ノ門店 |
| 8 | 銀座 | 35.67 / 139.76 | 銀座店 |
| 9 | 東銀座 | 35.67 / 139.77 | 歌舞伎座前東銀座店 |
| 10 | 麹町 | 35.68 / 139.74 | 麹町店 |
| 11 | 八重洲 | 35.68 / 139.77 | 東京八重洲口店 ※天気未取得 |
| 12 | 新宿 | 35.69 / 139.70 | 新宿東口店・新宿郵便局前店・新宿南口店 |
| 13 | 神田 | 35.69 / 139.77 | 神田南口店・神田東口店 ※天気未取得 |
| 14 | 水道橋 | 35.70 / 139.75 | 水道橋西口店 |
| 15 | お茶の水 | 35.70 / 139.76 | お茶の水店・本郷三丁目店 ※天気未取得 |
| 16 | 上野 | 35.71 / 139.78 | 上野浅草口店 |
| 17 | 池袋 | 35.73 / 139.71 | 池袋店 |
| 18 | 赤羽 | 35.78 / 139.72 | 赤羽店 |
| 19 | 松戸 | 35.78 / 139.90 | 松戸店 |
| 20 | 大宮 | 35.90 / 139.62 | 大宮そごう前店 ※天気未取得 |
| 21 | 川越 | 35.91 / 139.48 | 川越クレアモール店 |

> ※「天気未取得」= Open-Meteo API タイムアウトにより daily_weather にデータなし → 売上取得時に天気列が NULL になる。

---

### 2-6. daily_weather（日別天気データ）

| カラム名 | 型 | 説明 |
|---|---|---|
| location_id | INTEGER FK | 地点 ID（→ weather_locations） |
| date | DATE | 日付（JST 基準） |
| temperature_2m_max | NUMERIC(5,2) | 最高気温 (℃) |
| temperature_2m_min | NUMERIC(5,2) | 最低気温 (℃) |
| temperature_2m_mean | NUMERIC(5,2) | 平均気温 (℃) |
| precipitation_sum | NUMERIC(6,2) | 降水量 (mm) |
| weathercode | SMALLINT | WMO 天気コード |
| weather_label | TEXT | 日本語天気ラベル |
| fetched_at | TIMESTAMPTZ | 取得日時 |
| — | PK | (location_id, date) |

**インデックス:**

```sql
idx_daily_weather_loc_date   ON daily_weather(location_id, date)
```

**izakaya 関連地点のデータ量:**  
21地点 × 最大 731日分（2024-01-01 〜 2025-12-31）。ただし天気未取得の 4地点（11・13・15・20）は該当 location_id の行が欠損。

---

### 2-7. monthly_summary（月次集計キャッシュ）— V8 追加

`refresh_monthly_summary()` RPC が `order_items` を集計して書き込む事前計算テーブル。

| カラム名 | 型 | 説明 |
|---|---|---|
| id | SERIAL PK | — |
| store_id | INTEGER FK | 店舗 ID（→ stores） |
| store_name | TEXT | 店舗名（非正規化・高速参照用） |
| year_month | TEXT | 集計月（'YYYY-MM' 形式） |
| visit_count | INTEGER | 伝票数（来店件数） |
| total_revenue | NUMERIC(14,2) | 月間売上合計（円） |
| avg_unit_price | NUMERIC(10,2) | 平均客単価（円） |
| avg_party_size | NUMERIC(5,2) | 平均来店人数 |
| total_items_sold | INTEGER | 商品明細行数（重複除去後） |
| unique_items | INTEGER | ユニーク商品種類数 |
| top_item_name | TEXT | 最多注文商品名 |
| top_item_count | INTEGER | 最多注文商品の注文数 |
| drink_ratio | NUMERIC(5,4) | ドリンク比率（0.0〜1.0） |
| avg_stay_minutes | NUMERIC(8,2) | 平均滞在時間（分） |
| refreshed_at | TIMESTAMPTZ | 最終更新日時 |
| — | UNIQUE | (store_id, year_month) |

**インデックス:**

```sql
idx_monthly_summary_ym         ON monthly_summary(year_month)
idx_monthly_summary_store_ym   ON monthly_summary(store_id, year_month)
```

**ドリンク判定キーワード（`drink_ratio` 算出に使用）:**

```
ビール / 生ビール / 生中 / 生大 / ハイボール / チューハイ / 酎ハイ / サワー /
レモンサワー / ワイン / 日本酒 / 冷酒 / 熱燗 / 焼酎 / ホッピー / カクテル /
梅酒 / ウーロン茶 / お茶 / コーラ / ジュース / ノンアル / ドリンク / ソーダ
```

---

## 3. RPC 関数詳細

### 3-1. get_izakaya_sales（メイン取得）

```sql
get_izakaya_sales(
    p_start_date TEXT,       -- '2024-09-01'
    p_end_date   TEXT,       -- '2024-09-30'
    p_store_ids  INTEGER[]   -- NULL = 全店舗
)
```

| 設定 | 内容 |
|---|---|
| セキュリティ | `SECURITY DEFINER`（RLS バイパス） |
| タイムアウト | `SET LOCAL statement_timeout = '0'` |
| 重複除去 | `DISTINCT ON (visit_id, item_name, quantity, unit_price)` |
| 天気結合 | `LEFT JOIN daily_weather ON location_id + JST 日付` |
| 最適化 | `WITH filtered_visits AS MATERIALIZED` で先に visits を絞り込み |
| 権限 | anon, authenticated ロールに EXECUTE 付与 |

**返却カラム:**

| カラム名 | 型 | アプリ内日本語名 |
|---|---|---|
| receipt_no | TEXT | 伝票番号 |
| order_time | TIMESTAMPTZ | 注文日時 |
| visit_time | TIMESTAMPTZ | 来店時間 |
| leave_time | TIMESTAMPTZ | 退店時間 |
| party_size | INTEGER | 人数 |
| customer_layer | TEXT | 客層 |
| store_name | TEXT | 店舗名 |
| shop_code | TEXT | 店舗コード |
| item_name_raw | TEXT | 商品名 |
| quantity | INTEGER | 数量 |
| unit_price | NUMERIC | 単価 |
| temperature_2m_max | NUMERIC | （最高気温） |
| temperature_2m_min | NUMERIC | （最低気温） |
| temperature_2m_mean | NUMERIC | （平均気温） |
| precipitation_sum | NUMERIC | （降水量） |
| weathercode | SMALLINT | （WMO コード） |
| weather_label | TEXT | （天気ラベル） |

### 3-2. get_available_months（月一覧）

```sql
get_available_months(p_dataset TEXT DEFAULT 'izakaya')
-- 戻り値: TABLE(year_month TEXT)  例: '2024-09', '2025-09'
```

visits テーブルから JST 換算で月を DISTINCT 取得。アプリの月選択 UI に使用。

### 3-3. refresh_monthly_summary（集計再計算）

```sql
refresh_monthly_summary(p_year_month TEXT DEFAULT NULL)
-- p_year_month = NULL → 全月再計算
-- 戻り値: INTEGER（更新行数）
```

`order_items` を集計して `monthly_summary` に UPSERT。アプリ UI の「キャッシュ再生成」ボタンから呼び出し。

### 3-4. get_monthly_summary（集計取得）

```sql
get_monthly_summary(
    p_year_months TEXT[]    DEFAULT NULL,   -- NULL = 全月
    p_store_ids   INTEGER[] DEFAULT NULL    -- NULL = 全店舗
)
```

`monthly_summary` テーブルを軽量に SELECT する。全件 JOIN 不要で高速。

### 3-5. get_basket_pairs（バスケット分析）

```sql
get_basket_pairs(
    p_start_date TEXT,
    p_end_date   TEXT,
    p_store_ids  INTEGER[] DEFAULT NULL,
    p_top_n      INTEGER   DEFAULT 15       -- 分析対象とする商品上位N件
)
-- 戻り値: TABLE(item_a, item_b, co_count, item_a_count, item_b_count)
```

「同一伝票で一緒に注文された商品ペア」と共起回数を返す。DB 側で集計完結するため大量データでも高速。

---

## 4. アプリ側の処理

### 4-1. データ取得フロー（data_router.py）

```
POST /api/fetch
    │
    ├─ 選択月を 3日チャンクに分割（CHUNK_DAYS=3）
    ├─ 最大 2並列で get_izakaya_sales() を呼び出し（MAX_WORKERS=2）
    ├─ 1000行/ページでページネーション（RPC_PAGE_SIZE=1000）
    └─ 全チャンク結合 → _build_df() でカラム名を日本語化 → セッションに保存
```

### 4-2. カラム名マッピング（_build_df）

| RPC 返却カラム | DataFrame カラム | 備考 |
|---|---|---|
| visit_time | 来店時間 | |
| order_time | 注文日時 | |
| leave_time | 退店時間 | |
| receipt_no | 伝票番号 | |
| store_name | 店舗名 | |
| shop_code | 店舗コード | |
| item_name_raw | 商品名 | |
| quantity | 数量 | |
| unit_price | 単価 | |
| party_size | 人数 | |
| customer_layer | 客層 | |
| temperature_2m_* / precipitation_sum / weathercode / weather_label | 同名で保持 | |

**派生カラム（アプリ側で計算）:**

| カラム名 | 算出方法 |
|---|---|
| 合計金額(税込) | `unit_price × quantity` を `(来店時間, 伝票番号)` キーで合算 |

### 4-3. タイムゾーン処理

```
Supabase 格納: UTC（TIMESTAMPTZ）
アプリ表示:    JST（Asia/Tokyo = UTC+9）

変換例:
  visit_time = '2024-09-01 12:30:00 UTC'
  → JST 表示 '2024-09-01 21:30:00'

天気 JOIN の日付:
  (visit_time AT TIME ZONE 'Asia/Tokyo')::DATE
  → JST 基準の日付で daily_weather と照合
```

---

## 5. データ品質メモ

| 項目 | 内容 |
|---|---|
| **receipt_no の重複** | 伝票番号は店舗・日付をまたいで同じ番号が使われる場合がある。伝票カウントは `(来店時間, 伝票番号)` の複合キーで行うこと |
| **orders/order_items の重複** | 同一 visit_id に対して数百件の orders が存在する場合あり（複数回インポートが原因）。`get_izakaya_sales()` の `DISTINCT ON` で除去済み |
| **異常日付 visits** | 2026-02 / 2026-10 の visits（15件）を 2026-03-08 に削除済み |
| **天気未取得地点** | location_id 11（八重洲）・13（神田）・15（お茶の水）・20（大宮）は daily_weather が欠損。これらの店舗の天気列は NULL になる |
| **分析除外店舗** | SSOL幕張店（store_id=1）・本部情報システム店（7）・東神田研修センター店（8）はダミー/研修用データ |

---

## 6. 関連 SQL スクリプト

| ファイル | 内容 | 実行タイミング |
|---|---|---|
| `etc/supabase_setup.sql` | インデックス・タイムアウト設定・`get_izakaya_sales` RPC（最終版） | 初回セットアップ / RPC 更新時 |
| `etc/v8_migration.sql` | `monthly_summary` テーブル・`refresh_monthly_summary` / `get_monthly_summary` / `get_basket_pairs` RPC | V8 移行時（初回のみ） |
| `etc/create_daily_weather.sql` | `weather_locations` / `daily_weather` テーブル作成 | 天気機能追加時（初回のみ） |
| `etc/add_location_columns.sql` | `stores` への `location_id` カラム追加 | 天気機能追加時（初回のみ） |
| `etc/cleanup_visits_anomaly.sql` | 異常日付レコードの調査・削除 | 異常データ発生時 |

---

*このドキュメントは `docs/SUPABASE_IZAKAYA.md` に保存されています。*
