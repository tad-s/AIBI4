-- ============================================================
-- v8_migration.sql
-- V8向けDB追加オブジェクト
-- Supabase SQL Editor で実行してください
-- ============================================================

-- ────────────────────────────────────────────
-- Step 1: 追加インデックス（3年分データ対応）
-- ────────────────────────────────────────────

-- 店舗×日付の複合インデックス（月次集計クエリ高速化）
CREATE INDEX IF NOT EXISTS idx_visits_store_time
    ON visits(store_id, visit_time);

-- order_items の line_type='M' 部分インデックス（明細フィルタ高速化）
CREATE INDEX IF NOT EXISTS idx_order_items_type_order
    ON order_items(line_type, order_id)
    WHERE line_type = 'M';

-- visits の年月インデックス（月選択クエリ高速化）
CREATE INDEX IF NOT EXISTS idx_visits_yyyymm
    ON visits((date_trunc('month', visit_time AT TIME ZONE 'Asia/Tokyo')));

-- 商品名インデックス（バスケット分析・商品検索高速化）
CREATE INDEX IF NOT EXISTS idx_order_items_itemname
    ON order_items(item_name_raw)
    WHERE line_type = 'M';


-- ────────────────────────────────────────────
-- Step 2: monthly_summary テーブル（月次集計キャッシュ）
-- 3年分でも数百行の軽量テーブル。分析の高速化に使用。
-- ────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS monthly_summary (
    id                  SERIAL PRIMARY KEY,
    store_id            INTEGER NOT NULL REFERENCES stores(store_id),
    store_name          TEXT    NOT NULL,
    year_month          TEXT    NOT NULL,           -- 'YYYY-MM' 形式
    visit_count         INTEGER NOT NULL DEFAULT 0, -- 伝票数
    total_revenue       NUMERIC(14,2) NOT NULL DEFAULT 0, -- 売上合計
    avg_unit_price      NUMERIC(10,2),              -- 平均客単価
    avg_party_size      NUMERIC(5,2),               -- 平均人数
    total_items_sold    INTEGER DEFAULT 0,           -- 商品明細行数
    unique_items        INTEGER DEFAULT 0,           -- ユニーク商品数
    top_item_name       TEXT,                        -- 最多注文商品名
    top_item_count      INTEGER,                     -- 最多注文商品の注文数
    drink_ratio         NUMERIC(5,4),                -- ドリンク比率 (0.0-1.0)
    avg_stay_minutes    NUMERIC(8,2),                -- 平均滞在時間（分）
    refreshed_at        TIMESTAMPTZ DEFAULT now(),
    UNIQUE (store_id, year_month)
);

CREATE INDEX IF NOT EXISTS idx_monthly_summary_ym
    ON monthly_summary(year_month);
CREATE INDEX IF NOT EXISTS idx_monthly_summary_store_ym
    ON monthly_summary(store_id, year_month);

-- RLS設定
ALTER TABLE public.monthly_summary ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "anon_read_monthly"  ON public.monthly_summary;
DROP POLICY IF EXISTS "anon_write_monthly" ON public.monthly_summary;

CREATE POLICY "anon_read_monthly"
    ON public.monthly_summary FOR SELECT USING (true);
CREATE POLICY "anon_write_monthly"
    ON public.monthly_summary FOR ALL USING (true) WITH CHECK (true);


-- ────────────────────────────────────────────
-- Step 3: refresh_monthly_summary() RPC
-- 月次集計を再計算してmonthly_summaryにupsertする
-- ────────────────────────────────────────────

DROP FUNCTION IF EXISTS refresh_monthly_summary(TEXT);

CREATE OR REPLACE FUNCTION refresh_monthly_summary(
    p_year_month TEXT DEFAULT NULL  -- 'YYYY-MM' または NULL（全月再計算）
)
RETURNS INTEGER  -- 更新行数
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_count INTEGER := 0;
BEGIN
    SET LOCAL statement_timeout = '0';

    WITH base AS (
        -- DISTINCT ON で重複除去（既存 get_izakaya_sales と同じロジック）
        SELECT DISTINCT ON (v.visit_id, oi.item_name_raw, oi.quantity, oi.unit_price)
            v.store_id,
            s.store_name,
            to_char(v.visit_time AT TIME ZONE 'Asia/Tokyo', 'YYYY-MM') AS year_month,
            v.receipt_no,
            v.party_size,
            v.visit_time,
            v.leave_time,
            oi.item_name_raw,
            oi.quantity,
            oi.unit_price,
            (oi.unit_price * oi.quantity) AS line_total
        FROM visits v
        INNER JOIN stores s ON s.store_id = v.store_id
        INNER JOIN orders o ON o.visit_id = v.visit_id
        INNER JOIN order_items oi ON oi.order_id = o.order_id
        WHERE oi.line_type = 'M'
          AND (p_year_month IS NULL OR
               to_char(v.visit_time AT TIME ZONE 'Asia/Tokyo', 'YYYY-MM') = p_year_month)
        ORDER BY v.visit_id, oi.item_name_raw, oi.quantity, oi.unit_price, o.order_time
    ),
    visit_totals AS (
        SELECT store_id, store_name, year_month, receipt_no,
               SUM(line_total)   AS visit_revenue,
               MAX(party_size)   AS party_size,
               MIN(visit_time)   AS visit_time,
               MIN(leave_time)   AS leave_time
        FROM base
        GROUP BY store_id, store_name, year_month, receipt_no
    ),
    summary AS (
        SELECT
            store_id, store_name, year_month,
            COUNT(DISTINCT receipt_no)                         AS visit_count,
            SUM(visit_revenue)                                 AS total_revenue,
            AVG(visit_revenue)                                 AS avg_unit_price,
            AVG(party_size::NUMERIC)                           AS avg_party_size,
            AVG(EXTRACT(EPOCH FROM (leave_time - visit_time)) / 60) AS avg_stay_minutes
        FROM visit_totals
        GROUP BY store_id, store_name, year_month
    ),
    item_counts AS (
        SELECT store_id, year_month,
               COUNT(*)                     AS total_items_sold,
               COUNT(DISTINCT item_name_raw) AS unique_items
        FROM base
        GROUP BY store_id, year_month
    ),
    top_items AS (
        SELECT DISTINCT ON (store_id, year_month)
               store_id, year_month,
               item_name_raw AS top_item_name,
               COUNT(*)      AS top_item_count
        FROM base
        GROUP BY store_id, year_month, item_name_raw
        ORDER BY store_id, year_month, COUNT(*) DESC
    ),
    drink_kw AS (
        -- ドリンク判定（アプリ側と同じキーワード）
        SELECT store_id, year_month,
               SUM(CASE WHEN item_name_raw SIMILAR TO
                   '%(ビール|生ビール|生中|生大|ハイボール|チューハイ|酎ハイ|サワー|レモンサワー|ワイン|日本酒|冷酒|熱燗|焼酎|ホッピー|カクテル|梅酒|ウーロン茶|お茶|コーラ|ジュース|ノンアル|ドリンク|ソーダ)%'
                   THEN 1 ELSE 0 END)::NUMERIC AS drink_cnt,
               COUNT(*) AS total_cnt
        FROM base
        GROUP BY store_id, year_month
    )
    INSERT INTO monthly_summary (
        store_id, store_name, year_month,
        visit_count, total_revenue, avg_unit_price,
        avg_party_size, total_items_sold, unique_items,
        top_item_name, top_item_count, avg_stay_minutes,
        drink_ratio, refreshed_at
    )
    SELECT
        s.store_id, s.store_name, s.year_month,
        s.visit_count, s.total_revenue, s.avg_unit_price,
        s.avg_party_size,
        COALESCE(ic.total_items_sold, 0),
        COALESCE(ic.unique_items, 0),
        ti.top_item_name, ti.top_item_count::INTEGER,
        s.avg_stay_minutes,
        CASE WHEN dk.total_cnt > 0
             THEN (dk.drink_cnt / dk.total_cnt)
             ELSE NULL END,
        now()
    FROM summary s
    LEFT JOIN item_counts ic USING (store_id, year_month)
    LEFT JOIN top_items    ti USING (store_id, year_month)
    LEFT JOIN drink_kw     dk USING (store_id, year_month)
    ON CONFLICT (store_id, year_month) DO UPDATE SET
        visit_count      = EXCLUDED.visit_count,
        total_revenue    = EXCLUDED.total_revenue,
        avg_unit_price   = EXCLUDED.avg_unit_price,
        avg_party_size   = EXCLUDED.avg_party_size,
        total_items_sold = EXCLUDED.total_items_sold,
        unique_items     = EXCLUDED.unique_items,
        top_item_name    = EXCLUDED.top_item_name,
        top_item_count   = EXCLUDED.top_item_count,
        avg_stay_minutes = EXCLUDED.avg_stay_minutes,
        drink_ratio      = EXCLUDED.drink_ratio,
        refreshed_at     = now();

    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count;
END;
$$;

GRANT EXECUTE ON FUNCTION refresh_monthly_summary(TEXT) TO anon;
GRANT EXECUTE ON FUNCTION refresh_monthly_summary(TEXT) TO authenticated;


-- ────────────────────────────────────────────
-- Step 4: get_basket_pairs() RPC
-- バスケット分析をDB側で集計して返す（全件取得不要）
-- ────────────────────────────────────────────

DROP FUNCTION IF EXISTS get_basket_pairs(TEXT, TEXT, INTEGER[], INTEGER);

CREATE OR REPLACE FUNCTION get_basket_pairs(
    p_start_date TEXT,
    p_end_date   TEXT,
    p_store_ids  INTEGER[] DEFAULT NULL,
    p_top_n      INTEGER   DEFAULT 15
)
RETURNS TABLE(
    item_a       TEXT,
    item_b       TEXT,
    co_count     INTEGER,
    item_a_count INTEGER,
    item_b_count INTEGER
)
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    SET LOCAL statement_timeout = '0';

    RETURN QUERY
    WITH top_items AS (
        -- 出現頻度上位N商品を特定
        SELECT oi.item_name_raw,
               COUNT(DISTINCT v.receipt_no) AS freq
        FROM visits v
        INNER JOIN stores s  ON s.store_id  = v.store_id
        INNER JOIN orders o  ON o.visit_id  = v.visit_id
        INNER JOIN order_items oi ON oi.order_id = o.order_id
        WHERE oi.line_type = 'M'
          AND v.visit_time >= p_start_date::TIMESTAMPTZ
          AND v.visit_time <  (p_end_date::DATE + INTERVAL '1 day')::TIMESTAMPTZ
          AND (p_store_ids IS NULL OR v.store_id = ANY(p_store_ids))
        GROUP BY oi.item_name_raw
        ORDER BY freq DESC
        LIMIT p_top_n
    ),
    receipt_items AS (
        -- 上位N商品に絞った 伝票×商品 の組み合わせ（DISTINCT）
        SELECT DISTINCT v.receipt_no, oi.item_name_raw
        FROM visits v
        INNER JOIN orders o  ON o.visit_id  = v.visit_id
        INNER JOIN order_items oi ON oi.order_id = o.order_id
        INNER JOIN top_items ti ON ti.item_name_raw = oi.item_name_raw
        WHERE oi.line_type = 'M'
          AND v.visit_time >= p_start_date::TIMESTAMPTZ
          AND v.visit_time <  (p_end_date::DATE + INTERVAL '1 day')::TIMESTAMPTZ
          AND (p_store_ids IS NULL OR v.store_id = ANY(p_store_ids))
    ),
    pairs AS (
        -- 同一伝票内の全ペアと共起カウント
        SELECT
            LEAST(a.item_name_raw, b.item_name_raw)    AS item_a,
            GREATEST(a.item_name_raw, b.item_name_raw) AS item_b,
            COUNT(DISTINCT a.receipt_no)               AS co_count
        FROM receipt_items a
        INNER JOIN receipt_items b
            ON  a.receipt_no    = b.receipt_no
            AND a.item_name_raw < b.item_name_raw
        GROUP BY 1, 2
    )
    SELECT
        p.item_a,
        p.item_b,
        p.co_count::INTEGER,
        ta.freq::INTEGER AS item_a_count,
        tb.freq::INTEGER AS item_b_count
    FROM pairs p
    INNER JOIN top_items ta ON ta.item_name_raw = p.item_a
    INNER JOIN top_items tb ON tb.item_name_raw = p.item_b
    ORDER BY p.co_count DESC;
END;
$$;

GRANT EXECUTE ON FUNCTION get_basket_pairs(TEXT, TEXT, INTEGER[], INTEGER) TO anon;
GRANT EXECUTE ON FUNCTION get_basket_pairs(TEXT, TEXT, INTEGER[], INTEGER) TO authenticated;


-- ────────────────────────────────────────────
-- Step 5: fetch_monthly_summary RPC（軽量取得用）
-- ────────────────────────────────────────────

DROP FUNCTION IF EXISTS get_monthly_summary(TEXT[], INTEGER[]);

CREATE OR REPLACE FUNCTION get_monthly_summary(
    p_year_months TEXT[]    DEFAULT NULL,
    p_store_ids   INTEGER[] DEFAULT NULL
)
RETURNS TABLE(
    store_id        INTEGER,
    store_name      TEXT,
    year_month      TEXT,
    visit_count     INTEGER,
    total_revenue   NUMERIC,
    avg_unit_price  NUMERIC,
    avg_party_size  NUMERIC,
    total_items_sold INTEGER,
    unique_items    INTEGER,
    top_item_name   TEXT,
    top_item_count  INTEGER,
    drink_ratio     NUMERIC,
    avg_stay_minutes NUMERIC,
    refreshed_at    TIMESTAMPTZ
)
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    RETURN QUERY
    SELECT
        ms.store_id, ms.store_name, ms.year_month,
        ms.visit_count, ms.total_revenue, ms.avg_unit_price,
        ms.avg_party_size, ms.total_items_sold, ms.unique_items,
        ms.top_item_name, ms.top_item_count, ms.drink_ratio,
        ms.avg_stay_minutes, ms.refreshed_at
    FROM monthly_summary ms
    WHERE (p_year_months IS NULL OR ms.year_month = ANY(p_year_months))
      AND (p_store_ids   IS NULL OR ms.store_id   = ANY(p_store_ids))
    ORDER BY ms.store_id, ms.year_month;
END;
$$;

GRANT EXECUTE ON FUNCTION get_monthly_summary(TEXT[], INTEGER[]) TO anon;
GRANT EXECUTE ON FUNCTION get_monthly_summary(TEXT[], INTEGER[]) TO authenticated;
