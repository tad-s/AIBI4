-- ============================================================
-- PoC専用テーブル: poc_ikebukuro_items
--   テング酒場 池袋東口店（2026-03〜05）の、要件の除外を適用済みの
--   「商品明細(order粒度)」テーブル。原本(visits/orders/order_items)は不変。
--   1来店ID = visit_id。同時=order_id、連続=order_seq。
--   ※このDDLを実行後、担当(Claude)がRESTでデータ投入します（約60,603行）。
-- ============================================================

CREATE TABLE IF NOT EXISTS public.poc_ikebukuro_items (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    visit_id     text,          -- 1来店の正準ID（源泉UUID）
    store_id     text,
    receipt_no   text,
    party_size   integer,       -- 来店人数（この来店グループの人数）
    visit_start  timestamptz,   -- 来店時刻（UTC格納の正しいinstant。JST=UTC+9。INSERTは+09:00付きで投入しPostgresがUTCへ正規化→読出しは+00:00）
    order_id     text,          -- オーダー（同時注文の単位）
    order_seq    integer,       -- 来店内オーダー順（連続注文の判定に使用）
    line_index   integer,
    ordered_at   timestamptz,   -- 注文時刻（UTC格納の正しいinstant。JST=UTC+9。読出しは+00:00、JST変換で14-23時に収まる）
    item_name    text,
    category     text,          -- ドリンク/揚げ物/串/海鮮/鍋/サラダ/ヘビー/軽いつまみ/締め/デザート/その他
    fd           text,          -- 'ドリンク' or 'フード'
    quantity     numeric,
    unit_price   numeric,
    -- 2026-10-05 追加（9月データ投入時）。客層マスタのコード。00=未登録。
    customer_layer  text,        -- 客層1 = 年代（01=20~30代/02=30~40代/03=40~50代/04=50~60代/05=その他 ※並び順は要提供元確認）
    customer_layer2 text         -- 客層2 = 利用シーン（サラリーマン/会合/友人/学生/その他）。現状データは全'00'=未収集
);

-- 既存テーブルへの後付け（投入済み環境向け）:
-- ALTER TABLE public.poc_ikebukuro_items ADD COLUMN IF NOT EXISTS customer_layer  text;
-- ALTER TABLE public.poc_ikebukuro_items ADD COLUMN IF NOT EXISTS customer_layer2 text;

-- v9 は anon キーで参照するため、読み取りを許可する
ALTER TABLE public.poc_ikebukuro_items ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS poc_read_all ON public.poc_ikebukuro_items;
CREATE POLICY poc_read_all ON public.poc_ikebukuro_items
    FOR SELECT TO anon, authenticated USING (true);
GRANT SELECT ON public.poc_ikebukuro_items TO anon, authenticated;

-- 集約用インデックス
CREATE INDEX IF NOT EXISTS idx_poc_visit ON public.poc_ikebukuro_items(visit_id);
CREATE INDEX IF NOT EXISTS idx_poc_order ON public.poc_ikebukuro_items(order_id, order_seq);

-- 確認: 実行直後は 0 行（投入前）
SELECT count(*) AS rows_before_load FROM public.poc_ikebukuro_items;
