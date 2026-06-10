-- ============================================================
-- v8_weather_extend.sql
-- bakery / salon データセットへの天気統合
-- Supabase SQL Editor で実行してください
-- ============================================================
-- 前提条件:
--   ・v8_bakery_setup.sql が実行済み（bakery_stores テーブルが存在）
--   ・v8_salon_setup.sql が実行済み（salon_stores テーブルが存在）
--   ・create_daily_weather.sql が実行済み（weather_locations テーブルが存在）
-- ============================================================

-- ────────────────────────────────────────────
-- Step 1: location_id カラム追加
-- ────────────────────────────────────────────
ALTER TABLE bakery_stores ADD COLUMN IF NOT EXISTS
    location_id INTEGER REFERENCES weather_locations(location_id);

ALTER TABLE salon_stores ADD COLUMN IF NOT EXISTS
    location_id INTEGER REFERENCES weather_locations(location_id);

CREATE INDEX IF NOT EXISTS idx_bakery_stores_location ON bakery_stores(location_id);
CREATE INDEX IF NOT EXISTS idx_salon_stores_location  ON salon_stores(location_id);

-- ────────────────────────────────────────────
-- Step 2: 新規天気地点を追加（bakery / salon 専用エリア）
-- ────────────────────────────────────────────
INSERT INTO weather_locations (lat_grid, lon_grid, label) VALUES
    (35.70, 139.58, '吉祥寺'),
    (35.61, 139.67, '自由が丘'),
    (35.67, 139.71, '表参道')
ON CONFLICT (lat_grid, lon_grid) DO NOTHING;

-- ────────────────────────────────────────────
-- Step 3: 各店舗に location_id を設定（緯度経度グリッドで自動マッピング）
-- ────────────────────────────────────────────
UPDATE bakery_stores bs
SET location_id = wl.location_id
FROM weather_locations wl
WHERE round(bs.latitude::NUMERIC, 2)  = wl.lat_grid
  AND round(bs.longitude::NUMERIC, 2) = wl.lon_grid
  AND bs.latitude IS NOT NULL;

UPDATE salon_stores ss
SET location_id = wl.location_id
FROM weather_locations wl
WHERE round(ss.latitude::NUMERIC, 2)  = wl.lat_grid
  AND round(ss.longitude::NUMERIC, 2) = wl.lon_grid
  AND ss.latitude IS NOT NULL;

-- 確認用
-- SELECT store_name, latitude, longitude, location_id FROM bakery_stores;
-- SELECT store_name, latitude, longitude, location_id FROM salon_stores;

-- ────────────────────────────────────────────
-- Step 4: get_bakery_sales RPC に天気 JOIN を追加
-- ────────────────────────────────────────────
DROP FUNCTION IF EXISTS get_bakery_sales(TEXT, TEXT, INTEGER[]);

CREATE OR REPLACE FUNCTION get_bakery_sales(
    p_start_date TEXT,
    p_end_date   TEXT,
    p_store_ids  INTEGER[] DEFAULT NULL
)
RETURNS TABLE(
    receipt_no           TEXT,
    visit_time           TIMESTAMPTZ,
    leave_time           TIMESTAMPTZ,
    party_size           INTEGER,
    customer_layer       TEXT,
    store_name           TEXT,
    shop_code            TEXT,
    item_name_raw        TEXT,
    quantity             INTEGER,
    unit_price           NUMERIC,
    temperature_2m_max   NUMERIC,
    temperature_2m_min   NUMERIC,
    temperature_2m_mean  NUMERIC,
    precipitation_sum    NUMERIC,
    weathercode          SMALLINT,
    weather_label        TEXT
)
LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
    SET LOCAL statement_timeout = '0';
    SET search_path = public;
    RETURN QUERY
    WITH filtered_visits AS MATERIALIZED (
        SELECT v.visit_id,
               v.receipt_no,
               v.visit_time,
               v.leave_time,
               v.party_size::INTEGER AS party_size,
               v.customer_layer,
               v.store_id
        FROM public.bakery_visits v
        WHERE v.visit_time >= p_start_date::TIMESTAMPTZ
          AND v.visit_time <  (p_end_date::DATE + INTERVAL '1 day')::TIMESTAMPTZ
          AND (p_store_ids IS NULL OR v.store_id = ANY(p_store_ids))
    )
    SELECT DISTINCT ON (fv.visit_id, oi.item_name_raw, oi.quantity, oi.unit_price)
        fv.receipt_no,
        fv.visit_time,
        fv.leave_time,
        fv.party_size,
        fv.customer_layer,
        s.store_name,
        s.shop_code,
        oi.item_name_raw,
        oi.quantity::INTEGER AS quantity,
        oi.unit_price,
        dw.temperature_2m_max,
        dw.temperature_2m_min,
        dw.temperature_2m_mean,
        dw.precipitation_sum,
        dw.weathercode::SMALLINT,
        dw.weather_label
    FROM filtered_visits fv
    INNER JOIN public.bakery_stores      s  ON s.store_id  = fv.store_id
    INNER JOIN public.bakery_order_items oi ON oi.visit_id = fv.visit_id
    LEFT  JOIN public.daily_weather      dw
           ON  dw.location_id = s.location_id
           AND dw.date = (fv.visit_time AT TIME ZONE 'Asia/Tokyo')::DATE
    ORDER BY fv.visit_id, oi.item_name_raw, oi.quantity, oi.unit_price, fv.visit_time;
END;
$$;

GRANT EXECUTE ON FUNCTION get_bakery_sales(TEXT, TEXT, INTEGER[]) TO anon;
GRANT EXECUTE ON FUNCTION get_bakery_sales(TEXT, TEXT, INTEGER[]) TO authenticated;

-- ────────────────────────────────────────────
-- Step 5: get_salon_sales RPC に天気 JOIN を追加
-- ────────────────────────────────────────────
DROP FUNCTION IF EXISTS get_salon_sales(TEXT, TEXT, INTEGER[]);

CREATE OR REPLACE FUNCTION get_salon_sales(
    p_start_date TEXT,
    p_end_date   TEXT,
    p_store_ids  INTEGER[] DEFAULT NULL
)
RETURNS TABLE(
    receipt_no           TEXT,
    visit_time           TIMESTAMPTZ,
    leave_time           TIMESTAMPTZ,
    party_size           INTEGER,
    customer_layer       TEXT,
    store_name           TEXT,
    shop_code            TEXT,
    item_name_raw        TEXT,
    quantity             INTEGER,
    unit_price           NUMERIC,
    temperature_2m_max   NUMERIC,
    temperature_2m_min   NUMERIC,
    temperature_2m_mean  NUMERIC,
    precipitation_sum    NUMERIC,
    weathercode          SMALLINT,
    weather_label        TEXT
)
LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
    SET LOCAL statement_timeout = '0';
    SET search_path = public;
    RETURN QUERY
    WITH filtered_visits AS MATERIALIZED (
        SELECT v.visit_id,
               v.receipt_no,
               v.visit_time,
               v.leave_time,
               v.party_size::INTEGER AS party_size,
               v.customer_layer,
               v.store_id
        FROM public.salon_visits v
        WHERE v.visit_time >= p_start_date::TIMESTAMPTZ
          AND v.visit_time <  (p_end_date::DATE + INTERVAL '1 day')::TIMESTAMPTZ
          AND (p_store_ids IS NULL OR v.store_id = ANY(p_store_ids))
    )
    SELECT DISTINCT ON (fv.visit_id, oi.item_name_raw, oi.quantity, oi.unit_price)
        fv.receipt_no,
        fv.visit_time,
        fv.leave_time,
        fv.party_size,
        fv.customer_layer,
        s.store_name,
        s.shop_code,
        oi.item_name_raw,
        oi.quantity::INTEGER AS quantity,
        oi.unit_price,
        dw.temperature_2m_max,
        dw.temperature_2m_min,
        dw.temperature_2m_mean,
        dw.precipitation_sum,
        dw.weathercode::SMALLINT,
        dw.weather_label
    FROM filtered_visits fv
    INNER JOIN public.salon_stores      s  ON s.store_id  = fv.store_id
    INNER JOIN public.salon_order_items oi ON oi.visit_id = fv.visit_id
    LEFT  JOIN public.daily_weather     dw
           ON  dw.location_id = s.location_id
           AND dw.date = (fv.visit_time AT TIME ZONE 'Asia/Tokyo')::DATE
    ORDER BY fv.visit_id, oi.item_name_raw, oi.quantity, oi.unit_price, fv.visit_time;
END;
$$;

GRANT EXECUTE ON FUNCTION get_salon_sales(TEXT, TEXT, INTEGER[]) TO anon;
GRANT EXECUTE ON FUNCTION get_salon_sales(TEXT, TEXT, INTEGER[]) TO authenticated;
