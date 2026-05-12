-- ============================================================
-- cafe_setup.sql
-- カフェレストランデータセット用テーブル・RPC を Supabase SQL Editor で実行
-- ============================================================

-- ────────────────────────────────────────────
-- Step 1: テーブル作成
-- ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS cafe_stores (
    store_id        SERIAL PRIMARY KEY,
    store_name      TEXT,
    shop_code       TEXT,
    area_layer_name TEXT,
    address         TEXT,
    latitude        DOUBLE PRECISION,
    longitude       DOUBLE PRECISION,
    location_id     INTEGER REFERENCES weather_locations(location_id)
);

CREATE TABLE IF NOT EXISTS cafe_visits (
    visit_id        SERIAL PRIMARY KEY,
    store_id        INTEGER REFERENCES cafe_stores(store_id),
    receipt_no      TEXT,
    visit_time      TIMESTAMPTZ,
    leave_time      TIMESTAMPTZ,
    party_size      INTEGER,
    customer_layer  TEXT
);

CREATE TABLE IF NOT EXISTS cafe_orders (
    order_id    SERIAL PRIMARY KEY,
    visit_id    INTEGER REFERENCES cafe_visits(visit_id),
    order_time  TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS cafe_order_items (
    item_id       SERIAL PRIMARY KEY,
    order_id      INTEGER REFERENCES cafe_orders(order_id),
    item_name_raw TEXT,
    quantity      INTEGER,
    unit_price    NUMERIC,
    line_type     TEXT
);

-- ────────────────────────────────────────────
-- Step 2: インデックス
-- ────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_cafe_visits_visit_time     ON cafe_visits(visit_time);
CREATE INDEX IF NOT EXISTS idx_cafe_orders_visit_id       ON cafe_orders(visit_id);
CREATE INDEX IF NOT EXISTS idx_cafe_order_items_order_id  ON cafe_order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_cafe_order_items_line_type ON cafe_order_items(line_type);
CREATE INDEX IF NOT EXISTS idx_cafe_stores_location_id    ON cafe_stores(location_id);

-- ────────────────────────────────────────────
-- Step 3: 天気地点の追加（既存 weather_locations テーブルに追加）
-- 5地点: 恵比寿・川崎・藤沢・千葉・柏
-- ────────────────────────────────────────────
INSERT INTO weather_locations (lat_grid, lon_grid, label) VALUES
    (35.65, 139.71, '恵比寿'),
    (35.53, 139.70, '川崎'),
    (35.34, 139.49, '藤沢'),
    (35.61, 140.11, '千葉'),
    (35.86, 139.98, '柏')
ON CONFLICT (lat_grid, lon_grid) DO NOTHING;

-- ────────────────────────────────────────────
-- Step 4: RPC 関数 get_cafe_sales（get_izakaya_sales と同構造）
-- ────────────────────────────────────────────
DROP FUNCTION IF EXISTS get_cafe_sales(TEXT, TEXT, INTEGER[]);

CREATE OR REPLACE FUNCTION get_cafe_sales(
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
    WITH filtered_visits AS MATERIALIZED (
        SELECT v.visit_id,
               v.receipt_no,
               v.visit_time,
               v.leave_time,
               v.party_size::INTEGER AS party_size,
               v.customer_layer,
               v.store_id
        FROM cafe_visits v
        WHERE v.visit_time >= p_start_date::TIMESTAMPTZ
          AND v.visit_time <  (p_end_date::DATE + INTERVAL '1 day')::TIMESTAMPTZ
          AND (p_store_ids IS NULL OR v.store_id = ANY(p_store_ids))
    ),
    deduped AS (
        SELECT DISTINCT ON (fv.visit_id, oi.item_name_raw, oi.quantity, oi.unit_price)
            fv.receipt_no,
            o.order_time,
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
            dw.weathercode,
            dw.weather_label
        FROM filtered_visits fv
        INNER JOIN cafe_stores      s  ON s.store_id  = fv.store_id
        INNER JOIN cafe_orders      o  ON o.visit_id  = fv.visit_id
        INNER JOIN cafe_order_items oi ON oi.order_id = o.order_id
        LEFT  JOIN daily_weather    dw
               ON  dw.location_id = s.location_id
               AND dw.date = (fv.visit_time AT TIME ZONE 'Asia/Tokyo')::DATE
        WHERE oi.line_type = 'M'
        ORDER BY fv.visit_id, oi.item_name_raw, oi.quantity, oi.unit_price, o.order_time
    )
    SELECT
        d.receipt_no, d.order_time, d.visit_time, d.leave_time,
        d.party_size, d.customer_layer, d.store_name, d.shop_code,
        d.item_name_raw, d.quantity, d.unit_price,
        d.temperature_2m_max, d.temperature_2m_min, d.temperature_2m_mean,
        d.precipitation_sum, d.weathercode, d.weather_label
    FROM deduped d
    ORDER BY d.visit_time, d.receipt_no, d.order_time;
END;
$$;

-- ────────────────────────────────────────────
-- Step 5: 実行権限付与
-- ────────────────────────────────────────────
GRANT EXECUTE ON FUNCTION get_cafe_sales(TEXT, TEXT, INTEGER[]) TO anon;
GRANT EXECUTE ON FUNCTION get_cafe_sales(TEXT, TEXT, INTEGER[]) TO authenticated;

-- ────────────────────────────────────────────
-- Step 6: RLS ポリシー（anon 読み取り許可）
-- ────────────────────────────────────────────
ALTER TABLE cafe_stores      ENABLE ROW LEVEL SECURITY;
ALTER TABLE cafe_visits      ENABLE ROW LEVEL SECURITY;
ALTER TABLE cafe_orders      ENABLE ROW LEVEL SECURITY;
ALTER TABLE cafe_order_items ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "anon_read_cafe_stores"      ON cafe_stores;
DROP POLICY IF EXISTS "anon_read_cafe_visits"      ON cafe_visits;
DROP POLICY IF EXISTS "anon_read_cafe_orders"      ON cafe_orders;
DROP POLICY IF EXISTS "anon_read_cafe_order_items" ON cafe_order_items;

CREATE POLICY "anon_read_cafe_stores"      ON cafe_stores      FOR SELECT TO anon USING (true);
CREATE POLICY "anon_read_cafe_visits"      ON cafe_visits      FOR SELECT TO anon USING (true);
CREATE POLICY "anon_read_cafe_orders"      ON cafe_orders      FOR SELECT TO anon USING (true);
CREATE POLICY "anon_read_cafe_order_items" ON cafe_order_items FOR SELECT TO anon USING (true);

-- ────────────────────────────────────────────
-- Step 7: 動作確認クエリ（実行後に確認）
-- ────────────────────────────────────────────
-- SELECT COUNT(*) FROM cafe_visits;
-- SELECT COUNT(*) FROM get_cafe_sales('2024-09-01', '2024-09-30');
