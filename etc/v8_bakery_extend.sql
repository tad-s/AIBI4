-- ============================================================
-- v8_bakery_extend.sql  Farine ベーカリー データ拡張
-- 既存データを削除し、2024〜2025年の2年分を再生成します。
-- 前年比分析のための季節変動・成長トレンドを含みます。
-- Supabase SQL Editor で実行してください（所要時間: 約30秒）
-- ============================================================

-- 既存の売上データをリセット（stores は維持）
TRUNCATE bakery_order_items, bakery_visits RESTART IDENTITY CASCADE;

DO $$
DECLARE
    v_store   RECORD;
    v_day     DATE;
    v_vcnt    INT;
    v_vid     BIGINT;
    v_receipt TEXT;
    v_h       INT;
    v_bmin    INT;
    v_dur     INT;
    v_idx     INT;
    i         INT;
    j         INT;
    v_year    INT;
    v_month   INT;
    v_season  INT;  -- 季節係数
    -- 商品マスター
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
    -- モーニング〜夕方の来店時間帯（モーニング・ランチ・おやつ重み付き）
    v_hours   INT[]     := ARRAY[7,7,7,8,8,8,9,10,11,11,12,12,13,15,15,16,17,18];
    v_layers  TEXT[]    := ARRAY['新規','リピーター','リピーター','リピーター','会員'];
BEGIN
    FOR v_store IN SELECT * FROM bakery_stores LOOP
        FOR v_day IN
            SELECT d::DATE
            FROM generate_series('2024-01-01'::DATE, '2025-12-31'::DATE, '1 day') d
        LOOP
            v_year  := EXTRACT(YEAR  FROM v_day)::INT;
            v_month := EXTRACT(MONTH FROM v_day)::INT;

            -- 季節変動:
            --   春(3-5月)・秋(9-11月): お出かけ需要で好調 +2
            --   夏(7-8月): 暑さで朝客は増えるが昼減 ±0
            --   冬(12-2月): 温かいパンの需要 +1
            --   年末(12月): イベント需要 さらに +1
            v_season := CASE
                WHEN v_month IN (3,4,5)   THEN  2
                WHEN v_month IN (9,10,11) THEN  2
                WHEN v_month = 12         THEN  2
                WHEN v_month IN (1,2)     THEN  1
                ELSE                           0
            END;

            -- 2025年は成長トレンド（新店認知・リピーター増）+2
            v_season := v_season + CASE WHEN v_year = 2025 THEN 2 ELSE 0 END;

            v_vcnt := CASE
                WHEN EXTRACT(DOW FROM v_day) IN (0,6) THEN
                    GREATEST(8, 16 + v_season + floor(random()*8)::INT)
                ELSE
                    GREATEST(5,  9 + v_season + floor(random()*6)::INT)
            END;

            FOR i IN 1..v_vcnt LOOP
                v_h       := v_hours[1 + floor(random() * array_length(v_hours,1))::INT];
                v_bmin    := floor(random() * 55)::INT;
                v_dur     := 5 + floor(random() * 12)::INT;
                v_receipt := v_store.shop_code || TO_CHAR(v_day,'YYYYMMDD') || LPAD(i::TEXT,3,'0');

                INSERT INTO bakery_visits
                    (store_id, receipt_no, visit_time, leave_time, party_size, customer_layer)
                VALUES (
                    v_store.store_id,
                    v_receipt,
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
                        v_vid,
                        v_items[v_idx],
                        CASE WHEN random() < 0.72 THEN 1 ELSE 2 END,
                        v_prices[v_idx]
                    );
                END LOOP;
            END LOOP;
        END LOOP;
    END LOOP;

    RAISE NOTICE 'Farine ベーカリー 2024〜2025年データ生成完了';
END $$;
