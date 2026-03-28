# LLM BI アシスタント — アプリ仕様ドキュメント

> 最新バージョン: **v7.1** (`app_v7_1.py`)
> 前バージョン: v7.0 (`app_v7_0.py`)
> 起動コマンド: `streamlit run app_v7_1.py`
> 最終更新: 2026-03-29

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
┌──────────────────────────────────────────┐
│  Streamlit フロントエンド (app_v7_1.py)   │
│  - データ取得 UI                          │
│  - ベース分析（6項目）自動実行            │
│  - 分析指示チャット（音声入力対応）        │
│  - グラフ描画（matplotlib / exec()）      │
└──────────────┬───────────────────────────┘
               │
       ┌───────┴────────┐
       │                │
┌──────┴──────┐  ┌──────┴──────────┐
│  Supabase   │  │  OpenAI API     │
│  (PostgreSQL)│  │  gpt-4.1-mini  │
│  RPC: get_  │  │  whisper-1      │
│  izakaya_   │  │  （音声認識）   │
│  sales()    │  └─────────────────┘
└─────────────┘
       │
supabase_loader.py（共通モジュール）
  - get_client()                        ← HTTP timeout=120秒
  - fetch_stores()
  - fetch_available_months()
  - fetch_sales_data()                  ← CHUNK_DAYS=3、ページネーション対応
  - fetch_visits_for_summary()          ← キャッシュ生成用
  - fetch_daily_weather_by_store()      ← 将来用（現在未使用）
  - months_to_date_range()
```

### 主要定数（supabase_loader.py）

| 定数 | 値 | 説明 |
|---|---|---|
| `CHUNK_DAYS` | **3** | RPC 呼び出し1回あたりの日付範囲（タイムアウト対策で3日単位） |
| `RPC_PAGE_SIZE` | 1000 | PostgREST ページネーション行数 |

---

## 2. 画面レイアウト全体像

### v7.1（最新）

```
┌─────────────────────────────────────────────┐
│  🏮 LLM BI アシスタント                     │
│  ページタイトル + 説明文                    │
├─────────────────────────────────────────────┤
│  📊 データ概要サマリー（summary_cache）     │
│    ├─ 店舗 × 月 伝票数ヒートマップ          │
│    └─ 店舗 × 時間帯 伝票数ヒートマップ      │
│    └─ [🔄 キャッシュを再生成] ボタン        │
├─────────────────────────────────────────────┤
│  📅 DB からデータを取得                     │
│    ├─ 月選択（multiselect）                │
│    ├─ 店舗絞込（multiselect）              │
│    └─ [🔄 DB からデータを取得] ボタン       │
│       ↓ 取得完了でベース分析を自動起動      │
│    └─ 天気データ管理セクション              │
├─────────────────────────────────────────────┤
│  🧠 分析指示チャット（データ分析専用）      │  ← v7.1で上に移動・改名
│    ├─ [🎤 音声入力] / [⏹ 入力停止] ボタン  │  ← v7.1新機能
│    ├─ テキストエリア                       │
│    └─ [チャット内容でグラフを作成する]      │
├─────────────────────────────────────────────┤
│  🔬 ベース分析（6項目）                     │  ← v7.1で改名・自動実行
│    └─ DB取得後に自動表示（ボタン廃止）      │
└─────────────────────────────────────────────┘
```

### v7.0（旧）との主な差分

| 項目 | v7.0 | v7.1 |
|---|---|---|
| 初回自動分析 | あり（手動ボタン） | **廃止** |
| 追加分析（6項目） | 手動ボタンで実行 | **DB取得後に自動実行** |
| チャット欄の位置 | 最下部 | **追加分析の上（2番目）** |
| 音声入力 | なし | **Whisper 音声入力あり** |

---

## 3. セクション別 UI と動作詳細

### 3-1. ページヘッダー

- `st.set_page_config(page_title="LLM BI アシスタント", layout="wide")`
- 日本語フォントは matplotlib の `rcParams` で `IPAexGothic` / `Meiryo` / `Yu Gothic` をフォールバック順に設定

### 3-2. データ概要サマリー（`_show_summary_cache()`）

Supabase の `summary_cache` テーブルを読み込み、ヒートマップ2枚を表示する。

| 項目 | 内容 |
|---|---|
| データソース | Supabase `summary_cache` テーブル（visits テーブルベース） |
| ヒートマップ1 | 店舗 × 月　伝票数（`background_gradient(cmap="YlOrRd")`） |
| ヒートマップ2 | 店舗 × 時間帯　伝票数（〜17時/17〜20時/20〜23時/23時〜） |
| 再生成ボタン | `_rebuild_summary_cache()` で visits テーブルから再集計 → upsert |

**時間帯区分:**

| 区分 | 時間帯 |
|---|---|
| 〜17時 (昼) | 00:00〜16:59 JST |
| 17〜20時 (夕方) | 17:00〜19:59 JST |
| 20〜23時 (夜) | 20:00〜22:59 JST |
| 23時〜 (深夜) | 23:00〜23:59 JST |

**RLS 設定（summary_cache テーブル）:**

```sql
ALTER TABLE public.summary_cache ENABLE ROW LEVEL SECURITY;
CREATE POLICY "anon_read"  ON public.summary_cache FOR SELECT USING (true);
CREATE POLICY "anon_write" ON public.summary_cache FOR ALL USING (true) WITH CHECK (true);
```

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
3. `fetch_sales_data()` を呼び出し（3日チャンク・ページネーション）
4. プログレスバーで進捗表示
5. 全月分を `pd.concat()` で結合
6. 重複除去: `drop_duplicates(subset=["来店時間","伝票番号","商品名"])`
7. `st.session_state["df"]` に格納
8. **`st.session_state["show_additional"] = True` をセット → ベース分析が自動起動** ← v7.1

**伝票数カウント:**
```python
# 正しい方法（店舗・日付をまたぐ同一伝票番号に対応）
伝票数 = df.drop_duplicates(subset=["来店時間","伝票番号"]).shape[0]
```

### 3-4. 天気データの管理

DB データ取得後に `st.expander("🌤 天気データの管理")` 内に表示。

**「🔄 daily_weather テーブルを更新」ボタンの動作:**
1. `fetch_weather_for_stores.py` をインポート
2. `stores` テーブルの `latitude/longitude` から緯度経度取得（CSV 不要）
3. Open-Meteo Archive API で日別天気を取得
4. Supabase `daily_weather` テーブルに upsert
5. 完了後、売上データを再取得（天気が自動 JOIN される）

### 3-5. 分析指示チャット ← v7.1で改名・移動

> v7.0 では「追加の分析指示チャット」という名称で最下部にあった。
> v7.1 では「分析指示チャット」に改名し、DB取得セクションの直下に移動。

**音声入力（v7.1新機能）:**

| 項目 | 内容 |
|---|---|
| ライブラリ | `streamlit-mic-recorder==0.0.8` |
| 認識エンジン | OpenAI `whisper-1`（日本語指定） |
| ボタン | 「🎤 音声入力」→ 話す → 「⏹ 入力停止」 |
| 動作 | 録音完了後 Whisper で全文認識 → テキストエリアに一括入力 |

**チャット処理:**
- 曖昧マッチ（`build_fuzzy_context_for_chat()`）で店舗名補正
- `call_llm_chat()` でチャット履歴付き LLM 呼び出し
- グラフコードを `exec()` で実行・表示

### 3-6. ベース分析（6項目） ← v7.1で改名・自動実行

> v7.0 では「追加分析（6項目）」という名称で手動ボタンが必要だった。
> v7.1 では「ベース分析（6項目）」に改名し、DB取得後に自動実行。

`run_additional_analyses(df)` を呼び出し。

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

---

## 4. バックエンド処理詳細

### 4-1. データフロー（取得〜表示）

```
① fetch_sales_data(client, start, end, store_ids)
   └─ _week_ranges() で CHUNK_DAYS=3日のチャンクに分割
   └─ RPC get_izakaya_sales() を range(offset, offset+999) でページネーション
   └─ 結合 → 数値変換 → UTC→JST変換 → 合計金額計算 → 列名日本語化

② pd.concat() で全月分を結合

③ drop_duplicates(subset=["来店時間","伝票番号","商品名"]) で重複除去

④ st.session_state["df"] に格納
   + st.session_state["show_additional"] = True（ベース分析自動起動）
```

### 4-2. Supabase クライアント設定

```python
from supabase.lib.client_options import ClientOptions

def get_client() -> Client:
    return create_client(
        SUPABASE_URL, SUPABASE_KEY,
        options=ClientOptions(postgrest_client_timeout=120),  # 120秒
    )
```

### 4-3. サマリーキャッシュ（Supabase `summary_cache` テーブル）

```bash
python build_summary_cache.py  # バッチ実行
# または UI の「🔄 キャッシュを再生成」ボタン
```

- Supabase `visits` テーブルを全件ページネーション取得
- JST に変換して月・時間帯ごとに集計
- Supabase `summary_cache` テーブルに upsert（`id=1` の行を常に上書き）
- 未来月は自動除外

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

| 用途 | モデル |
|---|---|
| テキスト生成・グラフコード生成 | `gpt-4.1-mini` |
| 音声認識（v7.1） | `whisper-1`（language="ja"） |

### 5-2. グラフ品質ルール（`_GRAPH_QUALITY_RULES`）

| ルール | 内容 |
|---|---|
| 円単位 | 金額列のラベルに「（円）」を付ける |
| カンマ区切り | `ax.yaxis.set_major_formatter(FuncFormatter(...))` で3桁区切り |
| 空データガード | `if df.empty: raise ValueError(...)` を必ず含める |
| タイトル | すべてのグラフに `ax.set_title()` を設定 |
| フォント | `matplotlib.rcParams["font.family"]` に日本語フォントを設定 |

### 5-3. チャットプロンプト（`call_llm_chat()`）

- チャット履歴を `messages` リストで渡す（マルチターン対応）
- 店舗名の曖昧マッチ結果を `extra_system` として追加

---

## 6. 変更履歴

| 日付 | バージョン | 変更内容 |
|---|---|---|
| 2026-03-29 | - | APP_V7_0_SPEC.md を v7.1 対応に更新 |
| 2026-03-26 | v7.1 | `supabase_loader.py` タイムアウト対策: CHUNK_DAYS 7→3、HTTP timeout 120秒 |
| 2026-03-24 | v7.1 | `supabase_loader.py` ディスク満杯による空ファイル化を git restore で復元 |
| 2026-03-23 | v7.1 | `app_v7_1.py` 作成: 初回自動分析廃止、チャット欄移動・改名、ベース分析自動実行、音声入力追加 |
| 2026-03-22 | v7.0 | 音声入力（streamlit-mic-recorder + Whisper）を `app_v7_0.py` に追加 |
| 2026-03-22 | - | `summary_cache` テーブルに RLS 有効化・anon ポリシー設定 |
| 2026-03-22 | - | visits テーブルの 2026-03 テストデータ 11件削除（`receipt_no: APP-*`） |
| 2026-03-09 | v7.0 | APP_V7_0_SPEC.md 初版作成 |
| 2026-03-08 | v7.0 | visits の異常レコード（2026-02/10 分）15件削除 |
| 2026-03-07 | v7.0 | `profile_db.py` 依存を削除、`summary_cache` を Supabase テーブルベースに移行 |
| 2026-03-07 | v7.0 | PostgREST 1000行上限バグ修正（ページネーション追加） |
| 2026-03-07 | v7.0 | 伝票数カウントバグ修正（`drop_duplicates` 方式に変更） |
| 2026-03-07 | v7.0 | 天気データを RPC の LEFT JOIN で自動付与（手動結合を廃止） |
| 〜2026-03-06 | v7.0 | v7.0 初期デプロイ（git: `bdd8cf8`） |

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
streamlit-mic-recorder==0.0.8
```

### 7-2. 環境変数（`.env` または Streamlit Secrets）

| 変数名 | 説明 | 必須 |
|---|---|---|
| `SUPABASE_URL` | Supabase プロジェクト URL | ◎ |
| `SUPABASE_KEY` | Supabase anon key | ◎ |
| `OPENAI_API_KEY` | OpenAI API キー（GPT + Whisper 共用） | ◎ |

**ローカル:** `.env` ファイルに記載（git ignore 済み）
**クラウド:** Streamlit Cloud の Secrets 管理画面に登録

### 7-3. ファイル構成

```
AIBI4/
├── app_v7_1.py              # メインアプリ（最新）
├── app_v7_0.py              # 前バージョン（音声入力追加済み）
├── supabase_loader.py        # Supabase 接続・データ取得
├── build_summary_cache.py    # キャッシュ生成バッチ
├── fetch_weather_for_stores.py  # 天気データ取得バッチ
├── geocode_stores.py         # 店舗ジオコーディング
├── requirements.txt
├── .streamlit/
│   ├── config.toml           # maxUploadSize=50, theme=dark
│   └── secrets.toml          # ローカル用シークレット（git ignore）
├── data/
│   └── summary_cache.json    # ローカル用キャッシュ（Supabase テーブルが正本）
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
git add app_v7_1.py supabase_loader.py requirements.txt docs/
git commit -m "Deploy v7.1: 音声入力・ベース分析自動実行・タイムアウト対策"
git push origin master
```

> **注意:** `.env` と `.streamlit/secrets.toml` は絶対にコミットしない。

---

### Step 2: Streamlit Cloud でアプリを設定

1. https://share.streamlit.io にログイン
2. 「**New app**」をクリック
3. 以下を設定:

| 項目 | 設定値 |
|---|---|
| Repository | `あなたのGitHubユーザー名/AIBI4` |
| Branch | `master` |
| Main file path | `app_v7_1.py` |

---

### Step 3: Secrets（環境変数）を登録

「Advanced settings」→「Secrets」タブに以下を **TOML 形式** で入力:

```toml
SUPABASE_URL = "https://xxxxxxxxxxxxxxxxxx.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xxxxxxxx"
OPENAI_API_KEY = "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

---

### Step 4: デプロイ

「**Deploy!**」をクリック → ビルドログが表示される（2〜3分）。

---

### Step 5: 動作確認

- [ ] データ概要サマリー（ヒートマップ）が表示される
- [ ] 「DB からデータを取得」で月選択肢が表示される（Supabase 接続確認）
- [ ] データ取得完了後、ベース分析（6項目）が自動表示される
- [ ] 音声入力ボタンが表示され、録音・認識が動作する（OpenAI 接続確認）

---

### Step 6: 再デプロイ（コード更新時）

```bash
git add -p
git commit -m "修正内容の説明"
git push origin master
```

Streamlit Cloud は GitHub へのプッシュを検知して **自動的に再デプロイ**。

---

### トラブルシューティング

| エラー | 原因 | 対処 |
|---|---|---|
| `ModuleNotFoundError: supabase` | requirements.txt が読まれていない | ファイルがリポジトリルートにあるか確認 |
| `ModuleNotFoundError: streamlit_mic_recorder` | requirements.txt 未反映 | `streamlit-mic-recorder==0.0.8` が記載されているか確認 |
| `RuntimeError: get_izakaya_sales が存在しない` | RPC 関数未適用 | Supabase SQL Editor で `etc/supabase_setup.sql` を実行 |
| `SUPABASE_KEY が設定されていません` | Secrets 未登録 | Streamlit Cloud の Secrets に TOML を登録 |
| グラフが文字化け | 日本語フォント不在 | `packages.txt` に `fonts-noto-cjk` を記載 |
| タイムアウト（504） | RPC の負荷が高い | `CHUNK_DAYS` をさらに下げる（例: 2）、または選択月を減らす |
| 音声認識エラー | OpenAI API キー不正 / 残高不足 | OpenAI ダッシュボードで確認 |
| `summary_cache` RLS エラー | RLS ポリシー未設定 | Supabase SQL Editor でポリシーを追加（§3-2 参照） |
