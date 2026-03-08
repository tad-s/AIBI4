-- ============================================================
-- create_daily_weather.sql
-- 天気データ用テーブルを作成し、get_izakaya_sales RPC を更新する
-- Supabase SQL Editor で実行してください
-- ============================================================

-- ────────────────────────────────────────────
-- Step 1: weather_locations テーブル
--   ・lat_grid/lon_grid を 0.01° 精度でグリッド化
--   ・近接店舗が同じ地点の天気を共有できる
-- ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS weather_locations (
    location_id  SERIAL PRIMARY KEY,
    lat_grid     NUMERIC(7,4) NOT NULL,
    lon_grid     NUMERIC(7,4) NOT NULL,
    label        TEXT,
    UNIQUE (lat_grid, lon_grid)
);

-- ────────────────────────────────────────────
-- Step 2: daily_weather テーブル
--   ・PK = (location_id, date) で二重登録防止
--   ・weathercode は WMO 国際気象コード
-- ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS daily_weather (
    location_id          INTEGER      NOT NULL
                         REFERENCES weather_locations(location_id) ON DELETE CASCADE,
    date                 DATE         NOT NULL,
    temperature_2m_max   NUMERIC(5,2),
    temperature_2m_min   NUMERIC(5,2),
    temperature_2m_mean  NUMERIC(5,2),
    precipitation_sum    NUMERIC(6,2),
    weathercode          SMALLINT,
    weather_label        TEXT,
    fetched_at           TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (location_id, date)
);

CREATE INDEX IF NOT EXISTS idx_daily_weather_date   ON daily_weather (date);

-- ────────────────────────────────────────────
-- Step 3: stores テーブルに location_id 外部キー追加
-- ────────────────────────────────────────────
ALTER TABLE stores
    ADD COLUMN IF NOT EXISTS location_id INTEGER
    REFERENCES weather_locations(location_id);

CREATE INDEX IF NOT EXISTS idx_stores_location_id ON stores (location_id);

-- ────────────────────────────────────────────
-- Step 4: テーブル権限付与
-- ────────────────────────────────────────────
GRANT SELECT, INSERT, UPDATE ON weather_locations TO anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON daily_weather     TO anon, authenticated;
GRANT USAGE, SELECT ON SEQUENCE weather_locations_location_id_seq TO anon, authenticated;

-- ────────────────────────────────────────────
-- Step 5: RLS ポリシー設定
-- ────────────────────────────────────────────
ALTER TABLE weather_locations ENABLE ROW LEVEL SECURITY;
ALTER TABLE daily_weather     ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  -- weather_locations: 参照・追加
  IF NOT EXISTS (SELECT 1 FROM pg_policies
      WHERE tablename = 'weather_locations' AND policyname = 'anon_select_weather_locations') THEN
    CREATE POLICY "anon_select_weather_locations"
      ON weather_locations FOR SELECT TO anon USING (true);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies
      WHERE tablename = 'weather_locations' AND policyname = 'anon_insert_weather_locations') THEN
    CREATE POLICY "anon_insert_weather_locations"
      ON weather_locations FOR INSERT TO anon WITH CHECK (true);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies
      WHERE tablename = 'weather_locations' AND policyname = 'anon_update_weather_locations') THEN
    CREATE POLICY "anon_update_weather_locations"
      ON weather_locations FOR UPDATE TO anon USING (true) WITH CHECK (true);
  END IF;

  -- daily_weather: 参照・追加・更新（再取得による上書きを許可）
  IF NOT EXISTS (SELECT 1 FROM pg_policies
      WHERE tablename = 'daily_weather' AND policyname = 'anon_select_daily_weather') THEN
    CREATE POLICY "anon_select_daily_weather"
      ON daily_weather FOR SELECT TO anon USING (true);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies
      WHERE tablename = 'daily_weather' AND policyname = 'anon_insert_daily_weather') THEN
    CREATE POLICY "anon_insert_daily_weather"
      ON daily_weather FOR INSERT TO anon WITH CHECK (true);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies
      WHERE tablename = 'daily_weather' AND policyname = 'anon_update_daily_weather') THEN
    CREATE POLICY "anon_update_daily_weather"
      ON daily_weather FOR UPDATE TO anon USING (true) WITH CHECK (true);
  END IF;
END $$;

-- ────────────────────────────────────────────
-- Step 6: get_izakaya_sales RPC を天気列付きで更新
--   ・戻り型変更のため一度 DROP してから再作成
--   ・stores → weather_locations → daily_weather を LEFT JOIN
--   ・visit_time を JST 日付に変換して date と照合
--   ・天気データが未登録の日は NULL で返す（売上データは欠落しない）
-- ────────────────────────────────────────────
DROP FUNCTION IF EXISTS get_izakaya_sales(TEXT, TEXT, INTEGER[]);

CREATE OR REPLACE FUNCTION get_izakaya_sales(
    p_start_date TEXT,
    p_end_date   TEXT,
    p_store_ids  INTEGER[] DEFAULT NULL
)
RETURNS TABLE(
    receipt_no           TEXT,
    order_time           TIMESTAMPTZ,
    visit_time           TIMESTAMPTZ,
    leave_time           TIMESTAMPTZ,
    party_size           INTEGER,
    customer_layer       TEXT,
    store_name           TEXT,
    shop_code            TEXT,
    item_name_raw        TEXT,
    quantity             INTEGER,
    unit_price           NUMERIC,
    -- 天気列（天気データ未登録の日は NULL）
    temperature_2m_max   NUMERIC,
    temperature_2m_min   NUMERIC,
    temperature_2m_mean  NUMERIC,
    precipitation_sum    NUMERIC,
    weathercode          SMALLINT,
    weather_label        TEXT
)
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    SET LOCAL statement_timeout = '0';

    RETURN QUERY
    SELECT
        v.receipt_no,
        o.order_time,
        v.visit_time,
        v.leave_time,
        v.party_size::INTEGER,
        v.customer_layer,
        s.store_name,
        s.shop_code,
        oi.item_name_raw,
        oi.quantity::INTEGER,
        oi.unit_price,
        -- 天気（LEFT JOIN: 未取得日は NULL）
        dw.temperature_2m_max,
        dw.temperature_2m_min,
        dw.temperature_2m_mean,
        dw.precipitation_sum,
        dw.weathercode,
        dw.weather_label
    FROM visits v
    INNER JOIN stores       s  ON s.store_id    = v.store_id
    INNER JOIN orders       o  ON o.visit_id    = v.visit_id
    INNER JOIN order_items  oi ON oi.order_id   = o.order_id
    LEFT  JOIN daily_weather dw ON dw.location_id = s.location_id
                                AND dw.date = (v.visit_time AT TIME ZONE 'Asia/Tokyo')::DATE
    WHERE v.visit_time >= p_start_date::TIMESTAMPTZ
      AND v.visit_time <  (p_end_date::DATE + INTERVAL '1 day')::TIMESTAMPTZ
      AND oi.line_type = 'M'
      AND (p_store_ids IS NULL OR v.store_id = ANY(p_store_ids))
    ORDER BY v.visit_time, v.receipt_no, o.order_time;
END;
$$;

GRANT EXECUTE ON FUNCTION get_izakaya_sales(TEXT, TEXT, INTEGER[]) TO anon;
GRANT EXECUTE ON FUNCTION get_izakaya_sales(TEXT, TEXT, INTEGER[]) TO authenticated;

-- ────────────────────────────────────────────
-- 確認クエリ
-- ────────────────────────────────────────────
SELECT 'weather_locations' AS table_name, COUNT(*) AS row_count FROM weather_locations
UNION ALL
SELECT 'daily_weather',                   COUNT(*)               FROM daily_weather
UNION ALL
SELECT 'stores (location_id 設定済み)',    COUNT(*)               FROM stores WHERE location_id IS NOT NULL;
