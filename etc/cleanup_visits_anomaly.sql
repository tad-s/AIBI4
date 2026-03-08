-- ============================================================
-- cleanup_visits_anomaly.sql
-- visits テーブルの異常日付レコードを調査・削除する
-- 手順: Step 1 → 2 を確認してから Step 3 を実行
-- ============================================================

-- ────────────────────────────────────────────
-- Step 1: 月別レコード数の全体確認
--   → 2024-09 / 2024-10 / 2025-09 / 2025-10 以外の月があるか確認
-- ────────────────────────────────────────────
SELECT
    TO_CHAR((visit_time AT TIME ZONE 'Asia/Tokyo'), 'YYYY-MM') AS month_jst,
    COUNT(*) AS visit_count
FROM visits
WHERE visit_time IS NOT NULL
GROUP BY month_jst
ORDER BY month_jst;


-- ────────────────────────────────────────────
-- Step 2: 異常日付レコードの詳細確認
--   → 削除前に内容を目視確認してください
-- ────────────────────────────────────────────
SELECT
    v.visit_id,
    v.receipt_no,
    s.store_name,
    v.visit_time,
    (v.visit_time AT TIME ZONE 'Asia/Tokyo') AS visit_time_jst,
    v.party_size,
    v.customer_layer,
    -- 紐付く orders 数
    (SELECT COUNT(*) FROM orders o WHERE o.visit_id = v.visit_id) AS order_count,
    -- 紐付く order_items 数
    (SELECT COUNT(*) FROM order_items oi
        INNER JOIN orders o ON o.order_id = oi.order_id
        WHERE o.visit_id = v.visit_id) AS item_count
FROM visits v
LEFT JOIN stores s ON s.store_id = v.store_id
WHERE visit_time IS NOT NULL
  AND TO_CHAR((visit_time AT TIME ZONE 'Asia/Tokyo'), 'YYYY-MM')
      NOT IN ('2024-09', '2024-10', '2025-09', '2025-10')
ORDER BY visit_time;


-- ────────────────────────────────────────────
-- Step 3: 異常レコードの削除
--   ※ Step 1・2 で内容を確認してから実行してください
--   ※ orders / order_items に CASCADE DELETE が設定されていない場合は
--      先に order_items → orders の順で削除が必要です（下記参照）
-- ────────────────────────────────────────────

-- 3a: 異常 visit_id の一時収集
WITH anomaly_visits AS (
    SELECT visit_id
    FROM visits
    WHERE visit_time IS NOT NULL
      AND TO_CHAR((visit_time AT TIME ZONE 'Asia/Tokyo'), 'YYYY-MM')
          NOT IN ('2024-09', '2024-10', '2025-09', '2025-10')
)

-- 3b: order_items を先に削除（FK 制約対策）
DELETE FROM order_items
WHERE order_id IN (
    SELECT o.order_id
    FROM orders o
    INNER JOIN anomaly_visits av ON av.visit_id = o.visit_id
);

-- 3c: orders を削除
WITH anomaly_visits AS (
    SELECT visit_id
    FROM visits
    WHERE visit_time IS NOT NULL
      AND TO_CHAR((visit_time AT TIME ZONE 'Asia/Tokyo'), 'YYYY-MM')
          NOT IN ('2024-09', '2024-10', '2025-09', '2025-10')
)
DELETE FROM orders
WHERE visit_id IN (SELECT visit_id FROM anomaly_visits);

-- 3d: visits 本体を削除
DELETE FROM visits
WHERE visit_time IS NOT NULL
  AND TO_CHAR((visit_time AT TIME ZONE 'Asia/Tokyo'), 'YYYY-MM')
      NOT IN ('2024-09', '2024-10', '2025-09', '2025-10');

-- ────────────────────────────────────────────
-- Step 4: 削除後の確認
-- ────────────────────────────────────────────
SELECT
    TO_CHAR((visit_time AT TIME ZONE 'Asia/Tokyo'), 'YYYY-MM') AS month_jst,
    COUNT(*) AS visit_count
FROM visits
WHERE visit_time IS NOT NULL
GROUP BY month_jst
ORDER BY month_jst;


-- ────────────────────────────────────────────
-- Step 5（オプション）: 未来日付インサート防止の CHECK 制約
--   visits.visit_time が「現在時刻 + 1日」を超えるレコードを DB レベルで拒否する
--   ※ インポートパイプラインが同じ Supabase DB を使っている場合のみ有効
-- ────────────────────────────────────────────
ALTER TABLE visits
    ADD CONSTRAINT chk_visit_time_not_future
    CHECK (visit_time <= NOW() + INTERVAL '1 day');

-- 制約を削除したい場合（ロールバック用）:
-- ALTER TABLE visits DROP CONSTRAINT IF EXISTS chk_visit_time_not_future;
