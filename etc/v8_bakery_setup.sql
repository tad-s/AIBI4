-- ============================================================
-- v8_bakery_setup.sql  ベーカリーデータセット
-- Supabase SQL Editor で上から順に実行してください
-- ============================================================

-- ── Step 1: テーブル作成 ─────────────────────────────────
CREATE TABLE IF NOT EXISTS bakery_stores (
    store_id   SERIAL PRIMARY KEY,
    store_name TEXT NOT NULL,
    shop_code  TEXT,
    address    TEXT,
    latitude   DOUBLE PRECISION,
    longitude  DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS bakery_visits (
    visit_id       SERIAL PRIMARY KEY,
    store_id       INTEGER NOT NULL REFERENCES bakery_stores(store_id),
    receipt_no     TEXT NOT NULL,
    visit_time     TIMESTAMPTZ NOT NULL,
    leave_time     TIMESTAMPTZ,
    party_size     INTEGER DEFAULT 1,
    customer_layer TEXT
);

CREATE TABLE IF NOT EXISTS bakery_order_items (
    item_id       SERIAL PRIMARY KEY,
    visit_id      INTEGER NOT NULL REFERENCES bakery_visits(visit_id),
    item_name_raw TEXT NOT NULL,
    quantity      INTEGER DEFAULT 1,
    unit_price    NUMERIC(10,2) NOT NULL
);

-- ── Step 2: インデックス ──────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_bakery_visits_visit_time ON bakery_visits(visit_time);
CREATE INDEX IF NOT EXISTS idx_bakery_visits_store_id   ON bakery_visits(store_id);
CREATE INDEX IF NOT EXISTS idx_bakery_items_visit_id    ON bakery_order_items(visit_id);

-- ── Step 3: 店舗マスター ──────────────────────────────────
INSERT INTO bakery_stores (store_name, shop_code, address, latitude, longitude) VALUES
    ('Farine 渋谷店',    'BK001', '東京都渋谷区道玄坂1-2-3',       35.6580, 139.7016),
    ('Farine 新宿店',    'BK002', '東京都新宿区新宿3-14-1',         35.6896, 139.7006),
    ('Farine 銀座店',    'BK003', '東京都中央区銀座4-6-1',          35.6717, 139.7649),
    ('Farine 吉祥寺店',  'BK004', '東京都武蔵野市吉祥寺本町1-5-2',  35.7026, 139.5796),
    ('Farine 自由が丘店','BK005', '東京都目黒区自由が丘1-15-8',     35.6077, 139.6686)
ON CONFLICT DO NOTHING;

-- 既存データのブランド名更新（初回実行後に店舗名が変わった場合）
UPDATE bakery_stores SET store_name = 'Farine ' || store_name WHERE store_name NOT LIKE 'Farine%';

-- ── Step 4: RPC 関数（get_izakaya_sales と同一インターフェース）────
DROP FUNCTION IF EXISTS get_bakery_sales(TEXT, TEXT, INTEGER[]);

CREATE OR REPLACE FUNCTION get_bakery_sales(
    p_start_date TEXT,
    p_end_date   TEXT,
    p_store_ids  INTEGER[] DEFAULT NULL
)
RETURNS TABLE(
    receipt_no     TEXT,
    visit_time     TIMESTAMPTZ,
    leave_time     TIMESTAMPTZ,
    party_size     INTEGER,
    customer_layer TEXT,
    store_name     TEXT,
    shop_code      TEXT,
    item_name_raw  TEXT,
    quantity       INTEGER,
    unit_price     NUMERIC
)
LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
    SET LOCAL statement_timeout = '0';
    RETURN QUERY
    SELECT
        v.receipt_no,
        v.visit_time,
        v.leave_time,
        v.party_size::INTEGER,
        v.customer_layer,
        s.store_name,
        s.shop_code,
        oi.item_name_raw,
        oi.quantity::INTEGER,
        oi.unit_price
    FROM  bakery_visits      v
    JOIN  bakery_stores      s  ON s.store_id = v.store_id
    JOIN  bakery_order_items oi ON oi.visit_id = v.visit_id
    WHERE v.visit_time >= p_start_date::TIMESTAMPTZ
      AND v.visit_time <  (p_end_date::DATE + INTERVAL '1 day')::TIMESTAMPTZ
      AND (p_store_ids IS NULL OR v.store_id = ANY(p_store_ids))
    ORDER BY v.visit_time, v.receipt_no;
END;
$$;

-- ── Step 5: サンプルデータ生成（既存データがある場合はスキップ）────
DO $$
DECLARE
    v_store       RECORD;
    v_day         DATE;
    v_vcnt        INT;
    v_vid         BIGINT;
    v_receipt     TEXT;
    v_h           INT;
    v_bmin        INT;
    v_dur         INT;
    v_idx         INT;
    i             INT;
    j             INT;
    -- 商品マスター（名称と単価は同一インデックスで対応）
    v_items   TEXT[]    := ARRAY[
        'クロワッサン',  'あんパン',      'メロンパン',    'バゲット',      '食パン(1斤)',
        'チョココルネ',  'カスタードパン', 'カレーパン',    'チーズパン',    'レーズンパン',
        'シナモンロール','スコーン',      'クリームパン',   'ハムサンド',    'ホットサンド',
        'コーヒー',      'カフェオレ',    'カプチーノ',     'アイスコーヒー','オレンジジュース'
    ];
    v_prices  NUMERIC[] := ARRAY[
        220, 180, 200, 320, 280,
        160, 190, 210, 230, 200,
        300, 280, 190, 480, 520,
        380, 350, 400, 360, 320
    ];
    -- 来店時間帯（モーニング・ランチ・おやつタイム重み付き）
    v_hours   INT[]     := ARRAY[7,7,7,8,8,8,9,10,11,11,12,12,13,15,15,16,17,18];
    v_layers  TEXT[]    := ARRAY['新規','リピーター','リピーター','リピーター','会員'];
BEGIN
    IF EXISTS (SELECT 1 FROM bakery_visits LIMIT 1) THEN
        RAISE NOTICE '既存データあり → スキップ';
        RETURN;
    END IF;

    FOR v_store IN SELECT * FROM bakery_stores LOOP
        FOR v_day IN
            SELECT d::DATE
            FROM generate_series('2025-01-01'::DATE, '2025-03-31'::DATE, '1 day') d
        LOOP
            -- 来客数（土日は多め）
            v_vcnt := CASE
                WHEN EXTRACT(DOW FROM v_day) IN (0,6) THEN 16 + floor(random()*8)::INT
                ELSE                                       9  + floor(random()*6)::INT
            END;

            FOR i IN 1..v_vcnt LOOP
                v_h       := v_hours[1 + floor(random() * array_length(v_hours,1))::INT];
                v_bmin    := floor(random() * 55)::INT;
                v_dur     := 5 + floor(random() * 12)::INT;   -- 滞在 5〜16 分
                v_receipt := v_store.shop_code || TO_CHAR(v_day,'YYYYMMDD') || LPAD(i::TEXT,3,'0');

                INSERT INTO bakery_visits
                    (store_id, receipt_no, visit_time, leave_time, party_size, customer_layer)
                VALUES (
                    v_store.store_id, v_receipt,
                    (v_day::TIMESTAMP + make_interval(hours=>v_h, mins=>v_bmin)) AT TIME ZONE 'Asia/Tokyo',
                    (v_day::TIMESTAMP + make_interval(hours=>v_h, mins=>v_bmin+v_dur)) AT TIME ZONE 'Asia/Tokyo',
                    CASE WHEN random() < 0.82 THEN 1 ELSE 2 END,
                    v_layers[1 + floor(random() * array_length(v_layers,1))::INT]
                ) RETURNING visit_id INTO v_vid;

                -- 1〜3 商品/伝票
                FOR j IN 1..(1 + floor(random()*2.5)::INT) LOOP
                    v_idx := 1 + floor(random() * array_length(v_items,1))::INT;
                    INSERT INTO bakery_order_items (visit_id, item_name_raw, quantity, unit_price)
                    VALUES (
                        v_vid, v_items[v_idx],
                        CASE WHEN random() < 0.72 THEN 1 ELSE 2 END,
                        v_prices[v_idx]
                    );
                END LOOP;
            END LOOP;
        END LOOP;
    END LOOP;

    RAISE NOTICE 'ベーカリーサンプルデータ生成完了';
END $$;
