# v10 再開ガイド（PC再起動後）

## 現在の状態（2026-07-15 時点）

- **コミット済み**: `9501fd8` "Add v10: AI-native BI rebuild"（56ファイル）
- **push 未実施**（ローカル master のみ。リモート = github.com/tad-s/AIBI4）
- backend/frontend の依存は**インストール済み**（`.venv` と `node_modules` は再作成不要）
- `v10/backend/.env` は設定済み（Supabase / OpenAI キー）※gitignore 済み

## 再起動後の起動手順

### 方法A: ワンコマンド（推奨）

Git Bash で:

```bash
cd /c/Users/tarchi/AIBI4/v10 && ./start.sh
```

PowerShell で:

```powershell
cd C:\Users\tarchi\AIBI4\v10 ; .\start.ps1
```

→ backend(8000) と frontend(5173) が別ウィンドウで立ち上がる。
ブラウザで **http://localhost:5173** を開く。

### 方法B: 手動（2つのターミナル）

ターミナル1 — バックエンド:
```bash
cd /c/Users/tarchi/AIBI4/v10/backend
./.venv/Scripts/python.exe -m uvicorn main:app --reload --port 8000
```

ターミナル2 — フロントエンド:
```bash
cd /c/Users/tarchi/AIBI4/v10/frontend
npm run dev
```

## 動作確認

1. http://localhost:5173 を開く
2. 左サイドバーで期間（月）・店舗を選び「データを取得する」
3. タブ: 📊ダッシュボード / 🧭探索 / 🔬ベース分析 / 🔀注文導線分析

## 実装済み機能（このコミット時点）

- 構造化仕様 + DuckDB + セマンティック層（exec() 廃止）
- 12ベース分析（インタラクティブ ECharts）
- クロスフィルタ（クリックで全タイル連動）
- 探索モード（ピボットビルダー + ドリルダウン）
- タイル単位のグラフ切替、KPI 前期比デルタ + スパークライン
- AI ask（自然言語 → 仕様、query/clarify/impossible）

## 次にやる候補（未着手）

- リモートへ push
- Railway デプロイ（`v10/Dockerfile` + `v10/railway.json`、環境変数に SUPABASE_URL/KEY・OPENAI_API_KEY）
- ダッシュボード保存、Excel/エビデンス出力、認証、店舗/客層/天気フィルタUIの拡充
- 「その他」カテゴリ削減（`etc/item_category_master.sql` を Supabase 実行）
