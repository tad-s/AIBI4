-- ============================================================
-- v8_salon_setup.sql  美容院・サロンデータセット
-- Supabase SQL Editor で上から順に実行してください
--
-- データ設計:
--   visit = 予約/来店1件
--   order_items = 施術メニュー（メイン1件 + オプション0〜1件）
--   party_size は基本1（ペア来店は2）
-- ============================================================

-- ── Step 1: テーブル作成 ─────────────────────────────────
CREATE TABLE IF NOT EXISTS salon_stores (
    store_id   SERIAL PRIMARY KEY,
    store_name TEXT NOT NULL,
    shop_code  TEXT,
    address    TEXT,
    latitude   DOUBLE PRECISION,
    longitude  DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS salon_visits (
    visit_id       SERIAL PRIMARY KEY,
    store_id       INTEGER NOT NULL REFERENCES salon_stores(store_id),
    receipt_no     TEXT NOT NULL,
    visit_time     TIMESTAMPTZ NOT NULL,
    leave_time     TIMESTAMPTZ,
    party_size     INTEGER DEFAULT 1,
    customer_layer TEXT
);

CREATE TABLE IF NOT EXISTS salon_order_items (
    item_id       SERIAL PRIMARY KEY,
    visit_id      INTEGER NOT NULL REFERENCES salon_visits(visit_id),
    item_name_raw TEXT NOT NULL,
    quantity      INTEGER DEFAULT 1,
    unit_price    NUMERIC(10,2) NOT NULL
);

-- ── Step 2: インデックス ──────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_salon_visits_visit_time ON salon_visits(visit_time);
CREATE INDEX IF NOT EXISTS idx_salon_visits_store_id   ON salon_visits(store_id);
CREATE INDEX IF NOT EXISTS idx_salon_items_visit_id    ON salon_order_items(visit_id);

-- ── Step 3: 店舗マスター ──────────────────────────────────
INSERT INTO salon_stores (store_name, shop_code, address, latitude, longitude) VALUES
    ('Lumière 表参道本店',  'SL001', '東京都渋谷区神宮前5-1-1',    35.6652, 139.7121),
    ('Lumière 渋谷店',     'SL002', '東京都渋谷区宇田川町21-1',    35.6617, 139.6994),
    ('Lumière 銀座店',     'SL003', '東京都中央区銀座5-9-1',       35.6720, 139.7641),
    ('Lumière 新宿西口店',  'SL004', '東京都新宿区西新宿1-1-3',    35.6908, 139.6990),
    ('Lumière 自由が丘店',  'SL005', '東京都目黒区自由が丘2-9-1',  35.6079, 139.6679)
ON CONFLICT DO NOTHING;

-- 既存データのブランド名更新（初回実行後に店舗名が変わった場合）
UPDATE salon_stores SET store_name = 'Lumière ' || store_name WHERE store_name NOT LIKE 'Lumière%';

-- ── Step 4: RPC 関数 ─────────────────────────────────────
DROP FUNCTION IF EXISTS get_salon_sales(TEXT, TEXT, INTEGER[]);

CREATE OR REPLACE FUNCTION get_salon_sales(
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
    FROM  salon_visits      v
    JOIN  salon_stores      s  ON s.store_id = v.store_id
    JOIN  salon_order_items oi ON oi.visit_id = v.visit_id
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
    v_acnt        INT;
    v_vid         BIGINT;
    v_receipt     TEXT;
    v_h           INT;
    v_bmin        INT;
    v_dur         INT;
    v_idx         INT;
    v_opt_idx     INT;
    i             INT;
    -- 施術メニューマスター（名称・単価・標準所要時間[分]）
    v_items     TEXT[]    := ARRAY[
        'カット',          'カット(ロング)',  'カラー',          'カラー(ロング)',
        'パーマ',          'デジタルパーマ',  '縮毛矯正',        'ストレートパーマ',
        'ブリーチ',        'ハイライト',      'トリートメント',   'ヘッドスパ',
        '頭皮ケア',        'ネイルケア(手)',  'まつ毛エクステ',   '前髪カット',
        'キッズカット'
    ];
    v_prices    NUMERIC[] := ARRAY[
        6000,  7500,  12000, 14000,
        15000, 18000, 22000, 18000,
        9000,  14000,  5000,  4500,
        3500,   3800,  9000,  1500,
        3000
    ];
    -- 標準施術時間（分）—— leave_time 算出に使用
    v_durs      INT[]     := ARRAY[
        60,  75,  120, 150,
        150, 180, 180, 150,
        90,  150,  45,  45,
        30,   60,  90,  15,
        45
    ];
    -- オプションメニュー（トリートメント・ヘッドスパ系）インデックス範囲
    -- v_items[11..13] = トリートメント, ヘッドスパ, 頭皮ケア
    v_hours   INT[]    := ARRAY[10,10,11,11,12,13,13,14,14,15,15,16,17,18];
    v_layers  TEXT[]   := ARRAY['新規','リピーター','リピーター','VIP','会員'];
BEGIN
    IF EXISTS (SELECT 1 FROM salon_visits LIMIT 1) THEN
        RAISE NOTICE '既存データあり → スキップ';
        RETURN;
    END IF;

    FOR v_store IN SELECT * FROM salon_stores LOOP
        FOR v_day IN
            SELECT d::DATE
            FROM generate_series('2025-01-01'::DATE, '2025-03-31'::DATE, '1 day') d
        LOOP
            -- 火曜定休
            CONTINUE WHEN EXTRACT(DOW FROM v_day) = 2;

            v_acnt := CASE
                WHEN EXTRACT(DOW FROM v_day) IN (0,6) THEN 7 + floor(random()*4)::INT
                ELSE                                       4 + floor(random()*3)::INT
            END;

            FOR i IN 1..v_acnt LOOP
                -- メインメニューを先に決定 → 施術時間を確定
                v_idx  := 1 + floor(random() * array_length(v_items,1))::INT;
                v_dur  := v_durs[v_idx] + floor(random()*30)::INT;
                v_h    := v_hours[1 + floor(random() * array_length(v_hours,1))::INT];
                v_bmin := floor(random() * 50)::INT;
                v_receipt := v_store.shop_code || TO_CHAR(v_day,'YYYYMMDD') || LPAD(i::TEXT,3,'0');

                INSERT INTO salon_visits
                    (store_id, receipt_no, visit_time, leave_time, party_size, customer_layer)
                VALUES (
                    v_store.store_id, v_receipt,
                    (v_day::TIMESTAMP + make_interval(hours=>v_h, mins=>v_bmin)) AT TIME ZONE 'Asia/Tokyo',
                    (v_day::TIMESTAMP + make_interval(hours=>v_h, mins=>v_bmin+v_dur)) AT TIME ZONE 'Asia/Tokyo',
                    CASE WHEN random() < 0.95 THEN 1 ELSE 2 END,
                    v_layers[1 + floor(random() * array_length(v_layers,1))::INT]
                ) RETURNING visit_id INTO v_vid;

                -- メインメニュー（必須）
                INSERT INTO salon_order_items (visit_id, item_name_raw, quantity, unit_price)
                VALUES (v_vid, v_items[v_idx], 1, v_prices[v_idx]);

                -- オプション（トリートメント/ヘッドスパ）: 50%の確率で追加
                IF random() < 0.50 THEN
                    v_opt_idx := 11 + floor(random()*3)::INT;  -- 11〜13: トリートメント系
                    INSERT INTO salon_order_items (visit_id, item_name_raw, quantity, unit_price)
                    VALUES (v_vid, v_items[v_opt_idx], 1, v_prices[v_opt_idx]);
                END IF;

            END LOOP;
        END LOOP;
    END LOOP;

    RAISE NOTICE 'サロンサンプルデータ生成完了';
END $$;
