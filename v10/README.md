# AIBI4 v10 — AIネイティブ BI（プロトタイプ）

v7（Streamlit）〜v9（FastAPI + Vanilla JS / matplotlib PNG）を再設計した、
**実用BIツール**を目指す新アーキテクチャ。中核を先に立ち上げるプロトタイプ。

## 設計の核心

現行 v8/v9 の最大の弱点は「**LLMが matplotlib コードを生成 → `exec()` → 静止画PNG**」だった。
v10 はこれを構造的に置き換える。

```
自然言語 → LLM → QuerySpec（構造化JSON: 指標/軸/フィルタ/グラフ種別）
        → セマンティック層が決定論的に DuckDB SQL を生成・実行
        → フロントが ECharts でインタラクティブ描画
        → 気に入れば「AI分析」タイルとしてダッシュボードに残る
```

これにより:
- **`exec()` のセキュリティリスクと壊れやすさが構造的に消える**（LLMはコードを書かない）
- 集計ロジックが**1箇所（semantic/engine.py）に集約**され、テスト・監査可能
- チャートが**インタラクティブ**（ホバー・凡例・リサイズ）
- 結果が使い捨てPNGでなく**再利用可能なタイル**

## アーキテクチャ

```
v10/
├── backend/                     FastAPI + DuckDB
│   ├── core/
│   │   ├── config.py            環境変数
│   │   └── duck.py              セッション毎の DuckDB（items / orders 2テーブル）
│   ├── ingest/
│   │   ├── supabase_fetch.py    Supabase RPC 取得（ページネーション＋リトライ）
│   │   ├── transform.py         生行 → 商品明細 DataFrame（カテゴリ付与・除外）
│   │   └── categories.py        商品カテゴリ分類（9カテゴリ＋除外／正規化／マスタ）
│   ├── semantic/                ★セマンティック層
│   │   ├── model.py             指標(metric)・軸(dimension)の定義
│   │   ├── query.py             QuerySpec（pydantic）
│   │   ├── engine.py            QuerySpec → DuckDB SQL → 結果（唯一の集計経路）
│   │   └── presets.py           初期ダッシュボードのタイル定義
│   ├── llm/
│   │   └── spec_generator.py    自然言語 → QuerySpec（query/clarify/impossible）
│   ├── routers/                 meta / data(SSE) / query / ask
│   └── main.py
└── frontend/                    React + TypeScript + Vite + ECharts
    └── src/
        ├── state/store.ts       zustand によるアプリ状態
        ├── charts/buildOption.ts 結果 → ECharts オプション（bar/line/pie/area/table）
        └── components/          Sidebar / FilterBar / AskBar / KpiRow / ChartTile ...
```

### データモデル（DuckDB 内）

| テーブル | 粒度 | 用途 |
|---|---|---|
| `items`  | 1商品=1行 | 売上・販売点数、カテゴリ/商品別の内訳 |
| `orders` | 1来店=1行 | 客単価・注文数・人数・滞在・ドリンク比率など「1注文あたり」 |

指標は base（items/orders）を持ち、軸との整合性をエンジンが検証する。
例:「客単価（orders）× カテゴリ（items）」は不整合 → AIは `clarify` を返す。

## ローカル起動

### 1. バックエンド

```bash
cd v10/backend
python -m venv .venv
.venv/Scripts/activate          # Windows（macは source .venv/bin/activate）
pip install -r requirements.txt
cp .env.example .env            # SUPABASE_URL/KEY, OPENAI_API_KEY を設定
uvicorn main:app --reload --port 8000
```

### 2. フロントエンド

```bash
cd v10/frontend
npm install
npm run dev                     # http://localhost:5173（/api は 8000 にプロキシ）
```

ブラウザで <http://localhost:5173> を開く。

## 使い方

1. 左サイドバーでデータセット・分析期間（月）・店舗を選び「データを取得する」
2. KPI とダッシュボード（6タイル）が自動生成される
3. 上部フィルタ（期間・カテゴリ）で**全タイルが連動**して絞り込まれる
4. 上部の **AIバー**に自然言語で質問 → インタラクティブなタイルが「AI分析」に追加される
   - 曖昧な依頼は確認を返す（clarify）
   - データにない軸（年齢/性別など）は代替案を返す（impossible）

## デプロイ（Railway）

`v10/Dockerfile` がフロントをビルド → バックエンドに同梱し、FastAPI が静的配信する
単一サービス構成。環境変数に `SUPABASE_URL` `SUPABASE_KEY` `OPENAI_API_KEY` を設定する。

## 現状のスコープ（プロトタイプ）

- ✅ Supabase → DuckDB パイプライン、セマンティック層、9指標、9軸
- ✅ 初期ダッシュボード（KPI 6 + タイル 6）、グローバルフィルタ連動
- ✅ AI ask（NL→仕様、query/clarify/impossible）、インタラクティブ ECharts
- 🚧 未実装（拡張予定）: v9 の注文導線分析⑦〜⑫の移植、ダッシュボード保存、
  Excel/エビデンス出力、店舗・客層・天気フィルタのUI、ドリルダウン、認証
