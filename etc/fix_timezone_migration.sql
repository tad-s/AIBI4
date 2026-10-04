-- ============================================================
-- タイムゾーン是正マイグレーション（テング/OESデータ）
--
-- 問題:  OES取込時、JSTの壁時計(例 20:02)を +00:00(UTC) として保存していた。
--        JSTで表示/日付フィルタすると +9h ずれ、夕方の来店が翌日に漏れる。
--        （検証: 池袋 store_id=32 の 2026-05-01 来店組数が 128→107 に過少化していた）
-- 対策:  該当する業務時刻列を -9時間 補正する（壁時計がJSTとして正しくなる）。
-- 根拠:  ローカル原本 visits.csv と壁時計 100% 一致・全92日で補正後==原本を確認済み。
--
-- ⚠️ 必ず「一度だけ」実行すること（再実行すると -18h になり破損する）。
-- ⚠️ 実行前に必ず DB のバックアップ/スナップショットを取得すること（不可逆）。
-- ⚠️ created_at は実際の挿入時刻なので補正しない。
-- ============================================================

-- 【1. 実行前検証】以下は 107 と出るはず（＝ずれている状態）
SELECT count(DISTINCT visit_id) AS visits_2026_05_01_before
FROM visits
WHERE store_id = 32
  AND visit_time >= '2026-05-01 00:00:00+09'
  AND visit_time <  '2026-05-02 00:00:00+09';

-- 【2. 補正本体】必ずトランザクションで

BEGIN;

UPDATE visits SET
    visit_time  = visit_time  - interval '9 hours',
    leave_time  = leave_time  - interval '9 hours',
    visit_start = visit_start - interval '9 hours',
    visit_end   = visit_end   - interval '9 hours'
WHERE visit_start IS NOT NULL;   -- OES由来のみ（visit_start が NULL の混入行は除外）

UPDATE orders SET
    order_time = order_time - interval '9 hours';

UPDATE order_items SET
    ordered_at = ordered_at - interval '9 hours';

COMMIT;

-- 【3. 実行後検証】以下は 128 と出れば成功（原本CSVと一致）
SELECT count(DISTINCT visit_id) AS visits_2026_05_01_after
FROM visits
WHERE store_id = 32
  AND visit_time >= '2026-05-01 00:00:00+09'
  AND visit_time <  '2026-05-02 00:00:00+09';

-- 【4. 事後対応】
--  ・summary_cache 等の事前集計を使っている場合は再生成すること。
--  ・アプリ側(v8/v9/v10)の時刻処理は「UTCとして読み→JST変換」のままでよい
--    （DBが正しいUTCになったので、従来の tz_convert('Asia/Tokyo') が正しく機能する）。
