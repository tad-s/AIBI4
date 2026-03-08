-- ============================================================
-- create_summary_cache_table.sql
-- summary_cache テーブルの作成（Supabase SQL Editor で実行）
-- ============================================================

CREATE TABLE IF NOT EXISTS summary_cache (
    id            INTEGER PRIMARY KEY DEFAULT 1,  -- 常に1行のみ使用
    generated_at  TEXT    NOT NULL,               -- 生成日時 (ISO8601)
    total_visits  INTEGER NOT NULL DEFAULT 0,
    store_month   JSONB   NOT NULL DEFAULT '[]',  -- [{店舗名, month, 伝票数}, ...]
    store_timeband JSONB  NOT NULL DEFAULT '[]',  -- [{店舗名, time_band, 伝票数}, ...]
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);

-- 既存の行がない場合のみ初期行を挿入
INSERT INTO summary_cache (id, generated_at, total_visits, store_month, store_timeband)
VALUES (1, '未生成', 0, '[]', '[]')
ON CONFLICT (id) DO NOTHING;

-- anon / authenticated ロールに読み取り権限を付与
GRANT SELECT ON summary_cache TO anon;
GRANT SELECT ON summary_cache TO authenticated;

-- キャッシュ再生成時の書き込み権限（service_role はデフォルトで全権限あり）
-- アプリが anon キーで書き込む場合は以下も実行:
-- GRANT INSERT, UPDATE ON summary_cache TO anon;
-- GRANT INSERT, UPDATE ON summary_cache TO authenticated;
