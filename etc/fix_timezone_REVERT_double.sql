-- ============================================================
-- 【復旧用】タイムゾーン補正の二重適用を1回ぶん戻す（+9時間）
--
-- 経緯: fix_timezone_migration.sql の -9h UPDATE を誤って2回実行してしまい、
--       時刻が -18h（正しくは -9h）になっている。
--       このSQLで +9時間 を「1回だけ」加算し、正しい状態(-9h)に戻す。
--
-- ★★★ 最重要 ★★★
--  ・このSQLも「一度だけ」実行すること。
--  ・実行中に「Failed to fetch (api.supabase.com)」が出ても、それはブラウザの
--    タイムアウト表示にすぎず、サーバー側ではCOMMITが完走している可能性が高い。
--    → その場合でも【絶対に再実行しないこと】。まず担当(Claude)がRESTで検証する。
--  ・大きいテーブル(order_items 約105万行)対策として statement_timeout を無効化。
-- ============================================================

BEGIN;

SET LOCAL statement_timeout = 0;   -- サーバー側で完走させる（ブラウザが切れても継続）

UPDATE visits SET
    visit_time  = visit_time  + interval '9 hours',
    leave_time  = leave_time  + interval '9 hours',
    visit_start = visit_start + interval '9 hours',
    visit_end   = visit_end   + interval '9 hours'
WHERE visit_start IS NOT NULL;     -- -9h と同じ範囲

UPDATE orders SET
    order_time = order_time + interval '9 hours';

UPDATE order_items SET
    ordered_at = ordered_at + interval '9 hours';

COMMIT;

-- 【検証（参考）】池袋の最も早い来店時刻をJSTで確認。
--  復帰成功なら ランチ帯（11:xx〜12:xx JST）になる。
--  まだ二重補正のままなら 02:xx〜03:xx JST（早朝）になる。
SELECT min(visit_time AT TIME ZONE 'Asia/Tokyo') AS earliest_visit_jst_ikebukuro
FROM visits
WHERE store_id = 32;
