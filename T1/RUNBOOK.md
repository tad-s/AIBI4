# T1 池袋東口店レコメンドPoC 起動手順

T1はV8/V9を変更しない、PoC専用の独立ツールです。

## 対象

- 店舗: テング酒場 池袋東口店
- 期間: 2026年3月〜5月
- 時間: 全日14:00〜23:00、日曜のみ22:00まで
- 除外: 定食メニュー、分析対象外メニューCSV、お好みコース、飲み放題
- 単独客除外: `party_size >= 2`
- 高注文卓: 除外後の合計数量 `15品以上`

## 起動

```powershell
cd C:\Users\tarchi\AIBI4\T1\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn main:app --host 127.0.0.1 --port 8011 --reload
```

ブラウザで開く:

```text
http://127.0.0.1:8011/
```

## 操作

1. `基礎テーブル作成`
2. `分析実行`
3. 必要に応じて `Excel出力`

## 生成物

- `T1/data/t1_poc_base.csv`
- Excel出力: `T1_ikebukuro_poc_YYYYMMDD_HHMMSS.xlsx`

## 分析

1. 注文総数が多い卓の商品TOP10
2. 同時注文ペア TOP10
3. 連続注文ペア TOP10
4. 注文継続につながる商品組み合わせ各Top5

## 注意

- 原本データは変更しません。
- V8/V9/V10/V12は変更しません。
- 既存 `poc/` は参照元として残します。

## Railwayデプロイ

T1はV8/V9とは別サービスとしてRailwayに作成します。既存V8/V9サービスの設定は変更しません。

### 前提

RailwayではローカルCSVを使えないため、T1はSupabaseの `order_items` / `visits` から直接PoC基礎テーブルを作成します。

Railway Variables に以下を設定してください。

```env
SUPABASE_URL=...
SUPABASE_SERVICE_KEY=...
```

`SUPABASE_SERVICE_KEY` はRLS回避のためservice_role keyを推奨します。

### GitHub連携で作る場合

1. Railwayで `New Project` または既存Project内の `New Service`
2. `GitHub Repo` から `tad-s/AIBI4` を選択
3. Service Settingsで以下を設定
   - Root Directory: `T1`
   - Builder: `Dockerfile`
   - Dockerfile Path: `Dockerfile`
4. Variablesに `SUPABASE_URL` と `SUPABASE_SERVICE_KEY` を設定
5. Deploy
6. 発行されたURLで `/api/health` が `{"status":"ok","app":"T1"}` を返すことを確認

### CLIで作る場合

```powershell
cd C:\Users\tarchi\AIBI4\T1
railway init
railway up --path-as-root
```

CLI利用時も、Railway側でVariablesを設定してください。

### デプロイ後の操作

1. Railway URLを開く
2. `基礎テーブル作成`
3. `分析実行`
4. `Excel出力`
