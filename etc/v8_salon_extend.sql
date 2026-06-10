-- ============================================================
-- v8_salon_extend.sql  Lumière サロン データ拡張
-- 既存データを削除し、2024〜2025年の2年分を再生成します。
-- 前年比分析のための季節変動・成長トレンドを含みます。
-- Supabase SQL Editor で実行してください（所要時間: 約20秒）
-- ============================================================

-- 既存の売上データをリセット（stores は維持）
TRUNCATE salon_order_items, salon_visits RESTART IDENTITY CASCADE;

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
    v_year        INT;
    v_month       INT;
    v_season      INT;  -- 季節係数
    -- 施術メニューマスター（名称・単価・標準所要時間）
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
    v_durs      INT[]     := ARRAY[
        60,  75,  120, 150,
        150, 180, 180, 150,
        90,  150,  45,  45,
        30,   60,  90,  15,
        45
    ];
    v_hours   INT[]    := ARRAY[10,10,11,11,12,13,13,14,14,15,15,16,17,18];
    v_layers  TEXT[]   := ARRAY['新規','リピーター','リピーター','VIP','会員'];
BEGIN
    FOR v_store IN SELECT * FROM salon_stores LOOP
        FOR v_day IN
            SELECT d::DATE
            FROM generate_series('2024-01-01'::DATE, '2025-12-31'::DATE, '1 day') d
        LOOP
            -- 火曜定休
            CONTINUE WHEN EXTRACT(DOW FROM v_day) = 2;

            v_year  := EXTRACT(YEAR  FROM v_day)::INT;
            v_month := EXTRACT(MONTH FROM v_day)::INT;

            -- 季節変動:
            --   春(3-5月): イメチェン・成人式準備・新生活需要 +2
            --   秋(9-11月): 文化祭・七五三・忘年会準備 +2
            --   夏(6-8月): 梅雨〜夏のヘアケア・夏休み ±0
            --   冬(12月): 年末年始需要 +2
            --   年始(1月): 年明け閑散期 -1
            v_season := CASE
                WHEN v_month IN (3,4,5)   THEN  2
                WHEN v_month IN (9,10,11) THEN  2
                WHEN v_month = 12         THEN  2
                WHEN v_month = 1          THEN -1
                ELSE                           0
            END;

            -- 2025年は成長トレンド（SNS拡散・会員増） +1
            v_season := v_season + CASE WHEN v_year = 2025 THEN 1 ELSE 0 END;

            v_acnt := CASE
                WHEN EXTRACT(DOW FROM v_day) IN (0,6) THEN
                    GREATEST(3, 7 + v_season + floor(random()*4)::INT)
                ELSE
                    GREATEST(2, 4 + v_season + floor(random()*3)::INT)
            END;

            FOR i IN 1..v_acnt LOOP
                v_idx  := 1 + floor(random() * array_length(v_items,1))::INT;
                v_dur  := v_durs[v_idx] + floor(random()*30)::INT;
                v_h    := v_hours[1 + floor(random() * array_length(v_hours,1))::INT];
                v_bmin := floor(random() * 50)::INT;
                v_receipt := v_store.shop_code || TO_CHAR(v_day,'YYYYMMDD') || LPAD(i::TEXT,3,'0');

                INSERT INTO salon_visits
                    (store_id, receipt_no, visit_time, leave_time, party_size, customer_layer)
                VALUES (
                    v_store.store_id,
                    v_receipt,
                    (v_day::TIMESTAMP + make_interval(hours=>v_h, mins=>v_bmin)) AT TIME ZONE 'Asia/Tokyo',
                    (v_day::TIMESTAMP + make_interval(hours=>v_h, mins=>v_bmin+v_dur)) AT TIME ZONE 'Asia/Tokyo',
                    CASE WHEN random() < 0.95 THEN 1 ELSE 2 END,
                    v_layers[1 + floor(random() * array_length(v_layers,1))::INT]
                ) RETURNING visit_id INTO v_vid;

                -- メインメニュー（必須）
                INSERT INTO salon_order_items (visit_id, item_name_raw, quantity, unit_price)
                VALUES (v_vid, v_items[v_idx], 1, v_prices[v_idx]);

                -- オプション（トリートメント/ヘッドスパ）: 50%の確率
                IF random() < 0.50 THEN
                    v_opt_idx := 11 + floor(random()*3)::INT;
                    INSERT INTO salon_order_items (visit_id, item_name_raw, quantity, unit_price)
                    VALUES (v_vid, v_items[v_opt_idx], 1, v_prices[v_opt_idx]);
                END IF;

            END LOOP;
        END LOOP;
    END LOOP;

    RAISE NOTICE 'Lumière サロン 2024〜2025年データ生成完了';
END $$;
