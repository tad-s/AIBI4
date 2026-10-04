# Supabase DB 構造まとめ（V8 対応版）

> 作成日: 2026-06-23  
> 対象: V8 アプリ（FastAPI + Vanilla JS / Railway 本番）  
> Supabase プロジェクト: AIBI4

---

## 1. データセット一覧

V8 では 4 つのデータセットを切り替えて分析できる。各データセットは**専用テーブル群**と**共用 RPC 関数**で構成される。

| データセット | ブランド | データ期間 | 店舗数 |
|---|---|---|---|
| **izakaya** | テング酒場 / 大ホール（テンアライド） | 2024-09 〜 2025-10 | 15 店舗（分析対象） |
| **cafe** | Café（カフェレストラン） | 同上（izakaya と同データ期間） | 10 店舗 |
| **bakery** | Farine（ベーカリー） | 2024-01 〜 2025-12 | 5 店舗 |
| **salon** | Lumière（美容院・サロン） | 2024-01 〜 2025-12 | 5 店舗 |

---

## 2. 共有テーブル（全データセットで使用）

### 2-1. weather_locations（天気取得地点）

```sql
location_id  SERIAL PRIMARY KEY
lat_grid     NUMERIC(7,4)   -- 緯度グリッド（小数第2位まで）
lon_grid     NUMERIC(7,4)   -- 経度グリッド
label        TEXT           -- 代表エリア名
UNIQUE (lat_grid, lon_grid)
```

| 件数 | 備考 |
|---|---|
| 26 地点 | izakaya 21地点 + cafe 5地点（恵比寿・川崎・藤沢・千葉・柏）。bakery/salon 用 3地点（吉祥寺・自由が丘・表参道）は `v8_weather_extend.sql` で追加 |

### 2-2. daily_weather（日別天気データ）

```sql
location_id          INTEGER   NOT NULL  REFERENCES weather_locations(location_id)
date                 DATE      NOT NULL
temperature_2m_max   NUMERIC(5,2)   -- 最高気温 (℃)
temperature_2m_min   NUMERIC(5,2)   -- 最低気温 (℃)
temperature_2m_mean  NUMERIC(5,2)   -- 平均気温 (℃)
precipitation_sum    NUMERIC(6,2)   -- 降水量 (mm)
weathercode          SMALLINT       -- WMO 天気コード
weather_label        TEXT           -- 日本語天気ラベル（例: 晴れ, 雨）
fetched_at           TIMESTAMPTZ    DEFAULT now()
PRIMARY KEY (location_id, date)
```

| 件数 | データソース |
|---|---|
| 16,082 行（26地点 × 最大 731日分） | Open-Meteo Archive API（無料） |

**WMO 天気コード → 日本語ラベル 対応表（主なもの）**

| code | label | code | label |
|---|---|---|---|
| 0 | 快晴 | 61-65 | 雨（弱〜強） |
| 1 | 晴れ | 71-75 | 雪（弱〜強） |
| 3 | 曇り | 80-82 | にわか雨 |
| 51-55 | 霧雨 | 95 | 雷雨 |

---

## 3. izakaya データセット

### テーブル関係図

```
stores ─────────── location_id ──► weather_locations
  │ store_id                              │ location_id
  ▼                                       ▼
visits ◄── store_id                  daily_weather
  │ visit_id                         (location_id + date) PK
  ▼
orders
  │ order_id
  ▼
order_items

monthly_summary ◄── store_id（集計キャッシュ）
```

### stores（居酒屋 店舗マスタ）

```sql
store_id        SERIAL PRIMARY KEY
store_name      TEXT
shop_code       TEXT
area_layer_name TEXT
address         TEXT
latitude        DOUBLE PRECISION
longitude       DOUBLE PRECISION
location_id     INTEGER REFERENCES weather_locations(location_id)
```

**登録店舗: 30 件（うち分析対象: 15 店舗）**

| 主要店舗（抜粋） | location_id |
|---|---|
| テング酒場 名古屋松岡ビル店 | 1（名古屋） |
| テング酒場 渋谷西口桜丘店 | 5（渋谷） |
| 大ホール 新宿東口靖国通り店 | 12（新宿） |
| テング酒場 神田南口店 | 13（神田） |
| 大ホール 池袋店 | 17（池袋） |

### visits（来店記録）

```sql
visit_id        SERIAL PRIMARY KEY
store_id        INTEGER  REFERENCES stores(store_id)
receipt_no      TEXT
visit_time      TIMESTAMPTZ    -- UTC 格納
leave_time      TIMESTAMPTZ
party_size      INTEGER        -- 人数
customer_layer  TEXT           -- 客層
```

**データ量:**

| 件数 | 期間 | 対象月 |
|---|---|---|
| 939 件 | 2024-09-01 〜 2025-10-31 | 2024-09 / 2024-10 / 2025-09 / 2025-10 |

### orders（注文ヘッダ）

```sql
order_id   SERIAL PRIMARY KEY
visit_id   INTEGER REFERENCES visits(visit_id)
order_time TIMESTAMPTZ
```

> ⚠️ 重複インポートにより visits 1件に対して数百件が紐付く場合あり。RPC 内の `DISTINCT ON` で除去済み。

### order_items（注文明細）

```sql
item_id       SERIAL PRIMARY KEY
order_id      INTEGER REFERENCES orders(order_id)
item_name_raw TEXT
quantity      INTEGER
unit_price    NUMERIC
line_type     TEXT    -- 'M': 商品明細（分析対象）
```

**データ量: 約 282,983 行**（重複含む。RPC で DISTINCT ON 除去後は実質約 56,000 行程度）

### monthly_summary（月次集計キャッシュ）

V8 で追加。毎回 order_items を集計する代わりに事前集計結果を保持。

```sql
id               SERIAL PRIMARY KEY
store_id         INTEGER NOT NULL REFERENCES stores(store_id)
store_name       TEXT    NOT NULL
year_month       TEXT    NOT NULL    -- 'YYYY-MM'
visit_count      INTEGER             -- 伝票数
total_revenue    NUMERIC(14,2)       -- 月間売上合計（円）
avg_unit_price   NUMERIC(10,2)       -- 平均客単価（円）
avg_party_size   NUMERIC(5,2)        -- 平均人数
total_items_sold INTEGER             -- 商品明細行数（重複除去後）
unique_items     INTEGER             -- ユニーク商品数
top_item_name    TEXT                -- 最多注文商品名
top_item_count   INTEGER             -- 最多注文商品の注文数
drink_ratio      NUMERIC(5,4)        -- ドリンク比率（0.0〜1.0）
avg_stay_minutes NUMERIC(8,2)        -- 平均滞在時間（分）
refreshed_at     TIMESTAMPTZ         DEFAULT now()
UNIQUE (store_id, year_month)
```

---

## 4. cafe データセット

izakaya と同構造（`orders` テーブルを持つ点も同じ）。天気 JOIN 対応済み。

### テーブル関係図

```
cafe_stores ── location_id ──► weather_locations
     │                               │
     ▼                               ▼
cafe_visits ── store_id         daily_weather
     │
cafe_orders
     │
cafe_order_items
```

### cafe_stores

```sql
store_id        SERIAL PRIMARY KEY
store_name      TEXT
shop_code       TEXT
area_layer_name TEXT
address         TEXT
latitude        DOUBLE PRECISION
longitude       DOUBLE PRECISION
location_id     INTEGER REFERENCES weather_locations(location_id)
```

**登録店舗: 10 店舗（恵比寿・川崎・藤沢・千葉・柏 エリア）**

### cafe_visits

```sql
visit_id       SERIAL PRIMARY KEY
store_id       INTEGER REFERENCES cafe_stores(store_id)
receipt_no     TEXT
visit_time     TIMESTAMPTZ
leave_time     TIMESTAMPTZ
party_size     INTEGER
customer_layer TEXT
```

### cafe_orders

```sql
order_id   SERIAL PRIMARY KEY
visit_id   INTEGER REFERENCES cafe_visits(visit_id)
order_time TIMESTAMPTZ
```

### cafe_order_items

```sql
item_id       SERIAL PRIMARY KEY
order_id      INTEGER REFERENCES cafe_orders(order_id)
item_name_raw TEXT
quantity      INTEGER
unit_price    NUMERIC
line_type     TEXT    -- 'M': 商品明細（分析対象）
```

---

## 5. bakery データセット（Farine）

`orders` テーブルを持たないシンプル構成。`visit_id` に直接 `order_items` が紐付く。

### テーブル関係図

```
bakery_stores ── location_id ──► weather_locations（v8_weather_extend.sql 適用後）
      │                                  │
      ▼                                  ▼
bakery_visits ── store_id          daily_weather
      │
bakery_order_items
```

### bakery_stores

```sql
store_id   SERIAL PRIMARY KEY
store_name TEXT NOT NULL
shop_code  TEXT
address    TEXT
latitude   DOUBLE PRECISION
longitude  DOUBLE PRECISION
location_id INTEGER REFERENCES weather_locations(location_id)   -- ← v8_weather_extend.sql で追加
```

**登録店舗: 5 店舗**

| 店舗名 | shop_code | エリア |
|---|---|---|
| Farine 渋谷店 | BK001 | 渋谷 |
| Farine 新宿店 | BK002 | 新宿 |
| Farine 銀座店 | BK003 | 銀座 |
| Farine 吉祥寺店 | BK004 | 吉祥寺 |
| Farine 自由が丘店 | BK005 | 自由が丘 |

### bakery_visits

```sql
visit_id       SERIAL PRIMARY KEY
store_id       INTEGER NOT NULL REFERENCES bakery_stores(store_id)
receipt_no     TEXT NOT NULL
visit_time     TIMESTAMPTZ NOT NULL
leave_time     TIMESTAMPTZ
party_size     INTEGER DEFAULT 1
customer_layer TEXT    -- 新規 / リピーター / 会員
```

**データ量: 2024-01-01 〜 2025-12-31（2年分）**  
来店時間帯: モーニング(7〜9時)・ランチ・おやつタイム。土日は平日の約 1.5 倍の来客。

### bakery_order_items

```sql
item_id       SERIAL PRIMARY KEY
visit_id      INTEGER NOT NULL REFERENCES bakery_visits(visit_id)
item_name_raw TEXT NOT NULL
quantity      INTEGER DEFAULT 1
unit_price    NUMERIC(10,2) NOT NULL
```

**主な商品（20種）**

| カテゴリ | 商品 | 単価 |
|---|---|---|
| パン | クロワッサン・バゲット・食パン(1斤) | 180〜320円 |
| 菓子パン | あんパン・メロンパン・チョココルネ | 160〜200円 |
| 惣菜パン | カレーパン・チーズパン・ハムサンド | 210〜480円 |
| ドリンク | コーヒー・カフェオレ・カプチーノ | 350〜400円 |

---

## 6. salon データセット（Lumière）

施術時間が長い（30〜180分）ため `visit_time` / `leave_time` の差分が大きい。  
`orders` テーブルなし（`visit_id` に直接 `order_items` が紐付く）。

### テーブル関係図

```
salon_stores ── location_id ──► weather_locations（v8_weather_extend.sql 適用後）
     │                                │
     ▼                                ▼
salon_visits ── store_id         daily_weather
     │
salon_order_items
```

### salon_stores

```sql
store_id    SERIAL PRIMARY KEY
store_name  TEXT NOT NULL
shop_code   TEXT
address     TEXT
latitude    DOUBLE PRECISION
longitude   DOUBLE PRECISION
location_id INTEGER REFERENCES weather_locations(location_id)   -- ← v8_weather_extend.sql で追加
```

**登録店舗: 5 店舗**

| 店舗名 | shop_code | エリア |
|---|---|---|
| Lumière 表参道本店 | SL001 | 表参道 |
| Lumière 渋谷店 | SL002 | 渋谷 |
| Lumière 銀座店 | SL003 | 銀座 |
| Lumière 新宿西口店 | SL004 | 新宿 |
| Lumière 自由が丘店 | SL005 | 自由が丘 |

### salon_visits

```sql
visit_id       SERIAL PRIMARY KEY
store_id       INTEGER NOT NULL REFERENCES salon_stores(store_id)
receipt_no     TEXT NOT NULL
visit_time     TIMESTAMPTZ NOT NULL
leave_time     TIMESTAMPTZ
party_size     INTEGER DEFAULT 1   -- 基本1（ペア来店は2）
customer_layer TEXT    -- 新規 / リピーター / VIP / 会員
```

**データ量: 2024-01-01 〜 2025-12-31（2年分）**  
火曜定休。営業時間: 10〜18時。

### salon_order_items

```sql
item_id       SERIAL PRIMARY KEY
visit_id      INTEGER NOT NULL REFERENCES salon_visits(visit_id)
item_name_raw TEXT NOT NULL
quantity      INTEGER DEFAULT 1
unit_price    NUMERIC(10,2) NOT NULL
```

**主な施術メニュー（17種）**

| カテゴリ | メニュー | 単価 |
|---|---|---|
| カット | カット・カット(ロング) | 6,000〜7,500円 |
| カラー | カラー・カラー(ロング)・ブリーチ・ハイライト | 9,000〜14,000円 |
| パーマ | パーマ・デジタルパーマ・縮毛矯正 | 15,000〜22,000円 |
| トリートメント | トリートメント・ヘッドスパ・頭皮ケア | 3,500〜5,000円 |
| その他 | ネイルケア(手)・まつ毛エクステ・前髪カット | 1,500〜9,000円 |

---

## 7. RPC 関数一覧

### データ取得 RPC（全データセット共通インターフェース）

| RPC 名 | データセット | 天気 JOIN | DISTINCT ON |
|---|---|---|---|
| `get_izakaya_sales(p_start_date, p_end_date, p_store_ids[])` | izakaya | ✅ | ✅ |
| `get_cafe_sales(p_start_date, p_end_date, p_store_ids[])` | cafe | ✅ | ✅ |
| `get_bakery_sales(p_start_date, p_end_date, p_store_ids[])` | bakery | ✅（v8_weather_extend.sql 適用後） | — |
| `get_salon_sales(p_start_date, p_end_date, p_store_ids[])` | salon | ✅（v8_weather_extend.sql 適用後） | — |

**共通の返却カラム:**

| カラム名（英） | 型 | アプリ内日本語名 | 備考 |
|---|---|---|---|
| receipt_no | TEXT | 伝票番号 | |
| visit_time | TIMESTAMPTZ | 来店時間 | UTC → JST 変換して表示 |
| leave_time | TIMESTAMPTZ | 退店時間 | |
| party_size | INTEGER | 人数 | |
| customer_layer | TEXT | 客層 | |
| store_name | TEXT | 店舗名 | |
| shop_code | TEXT | 店舗コード | |
| item_name_raw | TEXT | 商品名 | |
| quantity | INTEGER | 数量 | |
| unit_price | NUMERIC | 単価 | |
| temperature_2m_max | NUMERIC | — | 最高気温 ℃（天気なし → NULL） |
| temperature_2m_min | NUMERIC | — | 最低気温 ℃ |
| temperature_2m_mean | NUMERIC | — | 平均気温 ℃ |
| precipitation_sum | NUMERIC | — | 降水量 mm |
| weathercode | SMALLINT | — | WMO コード |
| weather_label | TEXT | — | 日本語ラベル |

> **izakaya / cafe のみ**: `order_time`（TIMESTAMPTZ / 注文日時）も返却。

### izakaya 専用 RPC（V8 追加）

| RPC 名 | 役割 |
|---|---|
| `refresh_monthly_summary(p_year_month)` | monthly_summary テーブルを再計算・upsert |
| `get_monthly_summary(p_year_months[], p_store_ids[])` | monthly_summary から軽量取得 |
| `get_basket_pairs(p_start_date, p_end_date, p_store_ids[], p_top_n)` | バスケット分析（共起ペア集計） |

---

## 8. アプリ側でのカラム名マッピング

`data_router.py` の `_build_df()` が RPC の英語カラム名を日本語に変換する。

| RPC カラム名（英） | DataFrame カラム名（日） |
|---|---|
| visit_time | 来店時間 |
| order_time | 注文日時 |
| leave_time | 退店時間 |
| receipt_no | 伝票番号 |
| store_name | 店舗名 |
| shop_code | 店舗コード |
| item_name_raw | 商品名 |
| quantity | 数量 |
| unit_price | 単価 |
| party_size | 人数 |
| customer_layer | 客層 |

**派生列（アプリ側で計算）:**

| 日本語カラム名 | 算出方法 |
|---|---|
| 合計金額(税込) | `unit_price × quantity`（伝票単位で合算、`visit_time + receipt_no` をキーに） |
| 天気系列 | RPC から取得済み（temperature_*, precipitation_sum, weathercode, weather_label） |

---

## 9. SQL スクリプト実行順序

新規環境構築時の実行順序:

| # | ファイル | 内容 | タイミング |
|---|---|---|---|
| 1 | `etc/supabase_setup.sql` | izakaya 用インデックス・RPC（天気 JOIN + 重複除去） | 初期セットアップ |
| 2 | `etc/cafe_setup.sql` | cafe テーブル群・RPC・天気地点5件追加 | cafe 有効化時 |
| 3 | `etc/v8_migration.sql` | V8 用インデックス・monthly_summary テーブル・集計/バスケット RPC | V8 移行時 |
| 4 | `etc/v8_bakery_setup.sql` | bakery テーブル群・RPC・サンプルデータ | bakery 有効化時 |
| 5 | `etc/v8_salon_setup.sql` | salon テーブル群・RPC・サンプルデータ | salon 有効化時 |
| 6 | `etc/v8_bakery_extend.sql` | bakery データを 2024〜2025 年 2 年分に拡張 | 前年比分析用 |
| 7 | `etc/v8_salon_extend.sql` | salon データを 2024〜2025 年 2 年分に拡張 | 前年比分析用 |
| 8 | `etc/v8_weather_extend.sql` | bakery/salon に `location_id` 追加・天気 RPC 更新 | 天気機能統合時 |

---

## 10. データ品質・運用メモ

| 項目 | 内容 |
|---|---|
| タイムゾーン | Supabase は UTC 格納。アプリ表示・日付集計は JST（Asia/Tokyo）に変換 |
| izakaya 重複 | orders/order_items に約 4〜5 倍の重複行。RPC の `DISTINCT ON` で除去 |
| izakaya 異常日付 | 2026-02 / 2026-10 の visits は 2026-03-08 に削除済み |
| bakery/salon データ | PL/pgSQL で自動生成したサンプルデータ（季節変動・成長トレンド付き） |
| 天気データ取得 | `fetch_weather_all_datasets.py` で全地点分を Open-Meteo から一括取得 |
| 天気未取得地点 | location_id 11, 13, 15, 20 はタイムアウトにより未取得（2026-06-23 現在） |

---

*このドキュメントは `docs/SUPABASE_SCHEMA_V8.md` に保存されています。*
