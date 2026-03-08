-- ============================================================
-- add_location_columns.sql
-- stores テーブルに住所・位置情報カラムを追加する
-- Supabase SQL Editor で実行してください
-- ============================================================

-- Step 1: カラム追加
ALTER TABLE stores
  ADD COLUMN IF NOT EXISTS address    TEXT,
  ADD COLUMN IF NOT EXISTS latitude   DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS longitude  DOUBLE PRECISION;

-- Step 2: anon ロールに UPDATE 権限を付与（geocoding スクリプトが書き込めるよう）
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename = 'stores' AND policyname = 'anon_update_stores_location'
  ) THEN
    CREATE POLICY "anon_update_stores_location"
      ON stores
      FOR UPDATE
      TO anon
      USING (true)
      WITH CHECK (true);
  END IF;
END $$;

-- 確認クエリ
SELECT store_id, store_name, address, latitude, longitude FROM stores ORDER BY store_id;
