# LLM BI アシスタント — アプリ仕様ドキュメント

> 対象ファイル: `app_v7_0.py`
> 起動コマンド: `streamlit run app_v7_0.py`
> バージョン: v7.0
> 最終更新: 2026-03-09

---

## 目次
1. [アーキテクチャ概要](#1-アーキテクチャ概要)
2. [画面レイアウト全体像](#2-画面レイアウト全体像)
3. [セクション別 UI と動作詳細](#3-セクション別-ui-と動作詳細)
4. [バックエンド処理詳細](#4-バックエンド処理詳細)
5. [LLM 連携の仕様](#5-llm-連携の仕様)
6. [変更履歴](#6-変更履歴)
7. [依存関係・環境変数](#7-依存関係環境変数)
8. [デプロイ手順（Streamlit Community Cloud）](#8-デプロイ手順streamlit-community-cloud)

---

## 1. アーキテクチャ概要

```
┌──────────────────────────────────────┐
│  Streamlit フロントエンド (app_v7_0.py) │
│  - データ取得 UI                      │
│  - 自動分析・追加分析・チャット分析     │
│  - グラフ描画（matplotlib / exec()）   │
└──────────────┬───────────────────────┘
               │
       ┌───────┴────────┐
       │                │
┌──────┴──────┐  ┌──────┴──────────┐
│  Supabase   │  │  OpenAI API     │
│  (PostgreSQL)│  │  gpt-4.1-mini  │
│  RPC: get_  │  │                 │
│  izakaya_   │  └─────────────────┘
│  sales()    │
└─────────────┘
       │
supabase_loader.py（共通モジュール）
  - get_client()
  - fetch_stores()
  - fetch_available_months()
  - fetch_sales_data()          ← ページネーション対応 RPC 呼び出し
  - fetch_visits_for_summary()  ← キャッシュ生成用
  - fetch_daily_weather_by_store()  ← 将来用（現在未使用）
  - months_to_date_range()
```

### 主要定数（supabase_loader.py）

| 定数 | 値 | 説明 |
|---|---|---|
| `CHUNK_DAYS` | 30 | RPC 呼び出し1回あたりの日付範囲（月単位） |
| `RPC_PAGE_SIZE` | 1000 | PostgREST ページネーション行数 |

---

## 2. 画面レイアウト全体像

```
┌─────────────────────────────────────────────┐
│  🏮 居酒屋 LLM BI アシスタント             │
│  ページタイトル + 説明文                    │
├─────────────────────────────────────────────┤
│  📊 データ概要サマリー（summary_cache.json）│
│    ├─ 店舗 × 月 伝票数ヒートマップ          │
│    └─ 店舗 × 時間帯 伝票数ヒートマップ      │
│    └─ [🔄 キャッシュを再生成] ボタン        │
├─────────────────────────────────────────────┤
│  📅 DB からデータを取得                     │
│    ├─ 月選択（multiselect）                │
│    ├─ 店舗絞込（multiselect）              │
│    └─ [🔄 DB からデータを取得] ボタン       │
│    └─ 天気データ管理セクション              │
├─────────────────────────────────────────────┤
│  🧠 初回自動分析（LLM）                     │
│    └─ [🚀 初回自動分析を実行する] ボタン    │
│    └─ 分析結果テキスト + グラフグリッド     │
├─────────────────────────────────────────────┤
│  🔬 追加分析（6項目）                       │
│    └─ [🔬 追加分析を実行する] ボタン        │
│    └─ 6種の専門分析（ダミー or 実データ）   │
├─────────────────────────────────────────────┤
│  🧠 追加の分析指示チャット                  │
│    └─ テキストエリア + 生成ボタン           │
└─────────────────────────────────────────────┘
```

---

## 3. セクション別 UI と動作詳細

### 3-1. ページヘッダー

- `st.set_page_config(page_title="居酒屋 LLM BI", layout="wide")`
- タイトル: `🏮 居酒屋 LLM BI アシスタント`
- 日本語フォントは matplotlib の `rcParams` で `IPAexGothic` / `Meiryo` / `Yu Gothic` をフォールバック順に設定

### 3-2. データ概要サマリー（`_show_summary_cache()`）

`data/summary_cache.json` を読み込み、ヒートマップ2枚を表示する。

| 項目 | 内容 |
|---|---|
| データソース | `data/summary_cache.json`（visits テーブルベース） |
| ヒートマップ1 | 店舗 × 月　伝票数（`background_gradient(cmap="YlOrRd")`） |
| ヒートマップ2 | 店舗 × 時間帯　伝票数（〜17時/17〜20時/20〜23時/23時〜） |
| 再生成ボタン | `build_summary_cache.py` をインポートして `run()` 実行 |

**時間帯区分:**

| 区分 | 時間帯 |
|---|---|
| 〜17時 (昼) | 00:00〜16:59 JST |
| 17〜20時 (夕方) | 17:00〜19:59 JST |
| 20〜23時 (夜) | 20:00〜22:59 JST |
| 23時〜 (深夜) | 23:00〜23:59 JST |

### 3-3. DB データ取得

**月選択:**
- `fetch_available_months()` で visits テーブルから動的取得（TTL=300秒キャッシュ）
- フォールバック: `["2024-09", "2024-10", "2025-09", "2025-10"]`
- デフォルト: 最新2ヶ月を選択

**店舗絞込:**
- `fetch_stores()` で stores テーブルから全店舗取得
- 空=全店舗（`store_ids=None`）

**「🔄 DB からデータを取得」ボタン:**
1. 選択月を1ヶ月ずつループ
2. `months_to_date_range()` で日付範囲に変換
3. `fetch_sales_data()` を呼び出し（ページネーション・チャンク分割）
4. プログレスバーで進捗表示
5. 全月分を `pd.concat()` で結合
6. 重複除去: `drop_duplicates(subset=["来店時間","伝票番号","商品名"])`
7. `st.session_state["df"]` に格納

**取得後の表示:**
- 期間・伝票数・明細行数・天気データ付与状況をメトリクス表示
- 伝票数カウント: `df.drop_duplicates(subset=["来店時間","伝票番号"]).shape[0]`

### 3-4. 天気データの管理

DB データ取得後に `st.expander("🌤 天気データの管理")` 内に表示。

**表示内容:**
- 現在の天気データ付与状況（`temperature_2m_mean` の非 NULL 率）
- 「🔄 daily_weather テーブルを更新」ボタン

**「🔄 daily_weather テーブルを更新」ボタンの動作:**
1. `fetch_weather_for_stores.py` をインポート
2. `stores` テーブルの `latitude/longitude` から緯度経度取得（CSV 不要）
3. Open-Meteo Archive API で日別天気を取得
4. Supabase `daily_weather` テーブルに upsert
5. 完了後、売上データを再取得（天気が自動 JOIN される）

> **重要:** `stores` テーブルに `latitude/longitude` が設定されていない店舗は天気取得スキップ。

### 3-5. 初回自動分析（LLM）

**「🚀 初回自動分析を実行する」ボタンの動作:**
1. `build_data_summary(df, filename)` でデータサマリー文字列生成
2. `call_llm_for_initial_analysis(summary_text)` で GPT-4.1-mini 呼び出し
3. 応答から Markdown テキストと ` ```python ` コードブロックを抽出
4. グラフコードを `st.session_state["graphs"]` に追加
5. グラフを3列グリッドで表示（`render_graphs_grid()`）

**グラフ表示:**
- `st.image()` で PNG 表示
- カーソルホバーで拡大アイコン（Streamlit 標準）

### 3-6. 追加分析（6項目）

「🔬 追加分析を実行する」ボタン → `run_additional_analyses(df)` を呼び出し。

| No. | 分析名 | 手法 |
|---|---|---|
| ① | 客単価への影響変数（変数別） | 重回帰分析（説明変数: 曜日・時間帯・人数・FD比率等） |
| ② | 商品別 客単価への影響度 | 重回帰分析（商品を 0/1 エンコード） |
| ③ | ABC分析 + グループ別商品分析 | 客単価三分位でグルーピング |
| ④ | マーケットバスケット分析 | 商品の共起頻度分析 |
| ⑤ | 時系列・曜日別トレンド | 棒グラフ・折れ線グラフ |
| ⑥ | 滞在時間分析 | ヒストグラム・散布図 |

**ダミーデータ機能:**
- データ不足の場合はダミーデータで分析イメージを表示
- 「⚠️ ダミーデータによる分析イメージ」警告を表示
- 必要カラムを案内

### 3-7. チャット分析

- テキストエリアに自由分析指示を入力
- 「チャット内容でグラフを作成する」ボタン
- 曖昧マッチ（`build_fuzzy_context_for_chat()`）で店舗名補正
- `call_llm_chat()` でチャット履歴付き LLM 呼び出し
- グラフコードを `exec()` で実行・表示

---

## 4. バックエンド処理詳細

### 4-1. データフロー（取得〜表示）

```
① fetch_sales_data(client, start, end, store_ids)
   └─ _week_ranges() で CHUNK_DAYS=30日のチャンクに分割
   └─ RPC get_izakaya_sales() を range(offset, offset+999) でページネーション
   └─ 結合 → 数値変換 → UTC→JST変換 → 合計金額計算 → 列名日本語化

② pd.concat() で全月分を結合

③ drop_duplicates(subset=["来店時間","伝票番号","商品名"]) で重複除去

④ st.session_state["df"] に格納
```

### 4-2. 伝票数カウントの正確な方法

```python
# 正しい方法（店舗・日付をまたぐ同一伝票番号に対応）
伝票数 = df.drop_duplicates(subset=["来店時間","伝票番号"]).shape[0]

# NG: df["伝票番号"].nunique()  ← 月またぎ重複でアンダーカウント
```

### 4-3. サマリーキャッシュ生成（`build_summary_cache.py`）

```bash
python build_summary_cache.py  # バッチ実行
# または UI の「🔄 キャッシュを再生成」ボタン
```

- Supabase `visits` テーブルを全件ページネーション取得
- JST に変換して月・時間帯ごとに集計
- `data/summary_cache.json` に保存
- 未来月は自動除外（今月より後は警告して除外）

### 4-4. `sanitize_code()`

LLM 生成コードの実行前に以下を変換:

| 変換内容 | 理由 |
|---|---|
| `import ` 行を削除 | セキュリティ・名前空間制御 |
| `.append()` → `pd.concat()` | pandas 2.0 互換 |
| `plt.show()` を削除 | Streamlit 環境では不要 |

---

## 5. LLM 連携の仕様

### 5-1. 使用モデル

- プロバイダ: OpenAI
- モデル: `gpt-4.1-mini`

### 5-2. グラフ品質ルール（`_GRAPH_QUALITY_RULES`）

LLM へのシステムプロンプトに含まれる主なルール:

| ルール | 内容 |
|---|---|
| 円単位 | 金額列のラベルに「（円）」を付ける |
| カンマ区切り | `ax.yaxis.set_major_formatter(FuncFormatter(...))` で3桁区切り |
| 空データガード | `if df.empty: raise ValueError(...)` を必ず含める |
| タイトル | すべてのグラフに `ax.set_title()` を設定 |
| フォント | `matplotlib.rcParams["font.family"]` に日本語フォントを設定 |

### 5-3. 初回分析プロンプト（`call_llm_for_initial_analysis()`）

- システム: 居酒屋データ分析専門家の役割 + グラフ品質ルール
- ユーザー: `build_data_summary()` で生成したサマリー文字列
- 期待する応答: Markdown テキスト + Python グラフコードブロック（複数可）

### 5-4. チャットプロンプト（`call_llm_chat()`）

- チャット履歴を `messages` リストで渡す（マルチターン対応）
- 店舗名の曖昧マッチ結果を `extra_system` として追加

---

## 6. 変更履歴

| 日付 | 変更内容 |
|---|---|
| 2026-03-09 | APP_V7_0_SPEC.md 完全版作成（現在の実装を反映） |
| 2026-03-08 | visits の異常レコード（2026-02/10 分）15件削除 |
| 2026-03-07 | `profile_db.py` 依存を削除、`summary_cache` を Supabase ベースに移行 |
| 2026-03-07 | PostgREST 1000行上限バグ修正（ページネーション追加） |
| 2026-03-07 | 伝票数カウントバグ修正（`drop_duplicates` 方式に変更） |
| 2026-03-07 | 天気データを RPC の LEFT JOIN で自動付与（手動結合を廃止） |
| 〜2026-03-06 | v7.0 初期デプロイ（git: `bdd8cf8`） |

---

## 7. 依存関係・環境変数

### 7-1. requirements.txt

```
streamlit==1.52.1
openai==2.9.0
supabase==2.28.0
pandas==2.3.3
numpy==2.3.5
matplotlib==3.10.7
requests==2.32.5
python-dotenv==1.2.1
```

### 7-2. 環境変数（`.env` または Streamlit Secrets）

| 変数名 | 説明 | 必須 |
|---|---|---|
| `SUPABASE_URL` | Supabase プロジェクト URL | ◎ |
| `SUPABASE_KEY` | Supabase anon key | ◎ |
| `OPENAI_API_KEY` | OpenAI API キー | ◎ |

**ローカル:** `.env` ファイルに記載（git ignore 済み）
**クラウド:** Streamlit Cloud の Secrets 管理画面に登録

### 7-3. ファイル構成

```
AIBI4/
├── app_v7_0.py              # メインアプリ
├── supabase_loader.py        # Supabase 接続・データ取得
├── build_summary_cache.py    # キャッシュ生成バッチ
├── fetch_weather_for_stores.py  # 天気データ取得バッチ
├── geocode_stores.py         # 店舗ジオコーディング
├── requirements.txt
├── .streamlit/
│   ├── config.toml           # maxUploadSize=50, theme=dark
│   └── secrets.toml          # ローカル用シークレット（git ignore）
├── data/
│   └── summary_cache.json    # 事前集計キャッシュ
├── docs/
│   ├── APP_V7_0_SPEC.md     # 本ドキュメント
│   └── DB_SUMMARY.md        # DB 構造ドキュメント
└── etc/
    ├── supabase_setup.sql    # RPC 関数定義・インデックス（最終版）
    ├── add_location_columns.sql
    ├── create_daily_weather.sql
    ├── cleanup_visits_anomaly.sql
    └── fix_duplicate_rpc.sql  # 旧版（参照用のみ）
```

---

## 8. デプロイ手順（Streamlit Community Cloud）

### 前提条件

- GitHub アカウント（リポジトリが公開または Streamlit Cloud にアクセス権限あり）
- Streamlit Community Cloud アカウント（https://streamlit.io/cloud）
- Supabase プロジェクトが稼働中（RPC 関数適用済み）

---

### Step 1: GitHub にプッシュ

```bash
# リモートが設定済みか確認
git remote -v

# 変更をコミット
git add app_v7_0.py supabase_loader.py build_summary_cache.py \
        fetch_weather_for_stores.py requirements.txt \
        .streamlit/config.toml data/summary_cache.json \
        docs/ etc/
git commit -m "Deploy v7.0: Supabase連携・天気データ・LLM分析"

# プッシュ（初回は -u origin main）
git push origin main
```

> **注意:** `.env` と `.streamlit/secrets.toml` は絶対にコミットしない。
> `.gitignore` に含まれていることを確認。

---

### Step 2: Streamlit Cloud でアプリを作成

1. https://share.streamlit.io にログイン
2. 「**New app**」をクリック
3. 以下を設定:

| 項目 | 設定値 |
|---|---|
| Repository | `あなたのGitHubユーザー名/AIBI4` |
| Branch | `main` |
| Main file path | `app_v7_0.py` |

4. 「**Advanced settings**」をクリック

---

### Step 3: Secrets（環境変数）を登録

「Advanced settings」→「Secrets」タブに以下を **TOML 形式** で入力:

```toml
SUPABASE_URL = "https://xxxxxxxxxxxxxxxxxx.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xxxxxxxx"
OPENAI_API_KEY = "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

> 各値は Supabase ダッシュボード（Settings > API）と OpenAI ダッシュボードから取得。

---

### Step 4: デプロイ

「**Deploy!**」をクリック → ビルドログが表示される（2〜3分）。

ビルド完了後、`https://あなたのアプリ名.streamlit.app` でアクセス可能。

---

### Step 5: 動作確認

デプロイ後に以下を確認:

- [ ] アプリが起動し、データ概要サマリー（ヒートマップ）が表示される
- [ ] 「DB からデータを取得」で月選択肢が表示される（Supabase 接続確認）
- [ ] データ取得が正常に完了する
- [ ] 「初回自動分析を実行する」でグラフが生成される（OpenAI 接続確認）

---

### Step 6: 再デプロイ（コード更新時）

```bash
# ローカルで修正 → コミット → プッシュ
git add -p  # 変更ファイルを確認しながらステージ
git commit -m "修正内容の説明"
git push origin main
```

Streamlit Cloud は GitHub へのプッシュを検知して **自動的に再デプロイ**。
手動トリガーも可能: アプリ管理画面 → 「⋮」メニュー → 「Reboot app」

---

### トラブルシューティング

| エラー | 原因 | 対処 |
|---|---|---|
| `ModuleNotFoundError: supabase` | requirements.txt が読まれていない | ファイルがリポジトリルートにあるか確認 |
| `RuntimeError: get_izakaya_sales が存在しない` | RPC 関数未適用 | Supabase SQL Editor で `etc/supabase_setup.sql` を実行 |
| `SUPABASE_KEY が設定されていません` | Secrets 未登録 | Streamlit Cloud の Secrets に TOML を登録 |
| グラフが文字化け | 日本語フォント不在 | Streamlit Cloud には IPAexGothic が入らないため `Noto Sans CJK JP` 等に変更 |
| タイムアウト（504） | 月範囲が広すぎる | `CHUNK_DAYS` を 7 に下げる、または選択月を減らす |
