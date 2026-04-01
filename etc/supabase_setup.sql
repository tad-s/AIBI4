-- ============================================================
-- supabase_setup.sql
-- Supabase SQL Editor で実行してください（初回 or RPC 更新時）
-- ============================================================

-- ────────────────────────────────────────────
-- Step 1: インデックスの追加（JOIN・日付フィルタを高速化）
-- ────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_visits_visit_time      ON visits(visit_time);
CREATE INDEX IF NOT EXISTS idx_orders_visit_id        ON orders(visit_id);
CREATE INDEX IF NOT EXISTS idx_order_items_order_id   ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_order_items_line_type  ON order_items(line_type);
CREATE INDEX IF NOT EXISTS idx_daily_weather_loc_date ON daily_weather(location_id, date);
CREATE INDEX IF NOT EXISTS idx_stores_location_id     ON stores(location_id);

-- ────────────────────────────────────────────
-- Step 2: ステートメントタイムアウトの延長
-- ────────────────────────────────────────────
ALTER ROLE anon          SET statement_timeout = '0';
ALTER ROLE authenticated SET statement_timeout = '0';

-- ────────────────────────────────────────────
-- Step 3: 売上データ取得 RPC 関数（最終版）
--
-- ・DISTINCT ON で orders/order_items の重複行を DB レベルで除去
-- ・daily_weather を LEFT JOIN し、天気列を自動付与
--   （daily_weather にデータがない日は NULL で返る）
-- ・SECURITY DEFINER で RLS を回避
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
    -- 【最適化版】visits を先にインデックスで絞り込み（MATERIALIZED）、
    -- 絞り込んだ visit_id のみに orders/order_items を JOIN することで
    -- 大量重複データがある月でも高速動作する。
    WITH filtered_visits AS MATERIALIZED (
        -- Step1: idx_visits_visit_time を使って対象期間の visits だけ取得（小集合）
        SELECT v.visit_id,
               v.receipt_no,
               v.visit_time,
               v.leave_time,
               v.party_size::INTEGER AS party_size,
               v.customer_layer,
               v.store_id
        FROM visits v
        WHERE v.visit_time >= p_start_date::TIMESTAMPTZ
          AND v.visit_time <  (p_end_date::DATE + INTERVAL '1 day')::TIMESTAMPTZ
          AND (p_store_ids IS NULL OR v.store_id = ANY(p_store_ids))
    ),
    deduped AS (
        -- Step2: 小集合に対して JOIN → DISTINCT ON（処理行数を劇的に削減）
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
            oi.quantity::INTEGER        AS quantity,
            oi.unit_price,
            dw.temperature_2m_max,
            dw.temperature_2m_min,
            dw.temperature_2m_mean,
            dw.precipitation_sum,
            dw.weathercode,
            dw.weather_label
        FROM filtered_visits fv
        INNER JOIN stores       s  ON s.store_id    = fv.store_id
        INNER JOIN orders       o  ON o.visit_id    = fv.visit_id
        INNER JOIN order_items  oi ON oi.order_id   = o.order_id
        LEFT  JOIN daily_weather dw
               ON  dw.location_id = s.location_id
               AND dw.date = (fv.visit_time AT TIME ZONE 'Asia/Tokyo')::DATE
        WHERE oi.line_type = 'M'
        ORDER BY fv.visit_id, oi.item_name_raw, oi.quantity, oi.unit_price, o.order_time
    )
    SELECT
        d.receipt_no,
        d.order_time,
        d.visit_time,
        d.leave_time,
        d.party_size,
        d.customer_layer,
        d.store_name,
        d.shop_code,
        d.item_name_raw,
        d.quantity,
        d.unit_price,
        d.temperature_2m_max,
        d.temperature_2m_min,
        d.temperature_2m_mean,
        d.precipitation_sum,
        d.weathercode,
        d.weather_label
    FROM deduped d
    ORDER BY d.visit_time, d.receipt_no, d.order_time;
END;
$$;

-- ────────────────────────────────────────────
-- Step 4: 実行権限付与
-- ────────────────────────────────────────────
GRANT EXECUTE ON FUNCTION get_izakaya_sales(TEXT, TEXT, INTEGER[]) TO anon;
GRANT EXECUTE ON FUNCTION get_izakaya_sales(TEXT, TEXT, INTEGER[]) TO authenticated;

-- ────────────────────────────────────────────
-- Step 5: 動作確認クエリ（必要に応じて実行）
-- ────────────────────────────────────────────
-- SELECT COUNT(*) FROM get_izakaya_sales('2024-09-01', '2024-09-30');
-- SELECT receipt_no, store_name, temperature_2m_max, weather_label
--   FROM get_izakaya_sales('2024-09-01', '2024-09-07')
--  LIMIT 10;
