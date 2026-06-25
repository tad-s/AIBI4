# AIBI4 V8 開発ガイド

最終更新: 2026-06-26

---

## 目次
1. [システム概要](#1-システム概要)
2. [ファイル構成](#2-ファイル構成)
3. [環境構築・起動手順](#3-環境構築起動手順)
4. [アーキテクチャ詳細](#4-アーキテクチャ詳細)
5. [APIエンドポイント一覧](#5-apiエンドポイント一覧)
6. [重要な実装上の注意点（バグ修正履歴）](#6-重要な実装上の注意点バグ修正履歴)
7. [フロントエンド構成](#7-フロントエンド構成)
8. [今後の開発課題](#8-今後の開発課題)

---

## 1. システム概要

居酒屋チェーン向け LLM BI アシスタントの第8世代。

| 項目 | 内容 |
|------|------|
| バックエンド | FastAPI + uvicorn |
| フロントエンド | Vanilla JS（ES Modules）|
| データソース | Supabase（PostgreSQL）|
| LLM | OpenAI gpt-4.1-mini |
| 音声入力 | OpenAI Whisper |
| グラフ生成 | matplotlib（Agg バックエンド）|

**V7との主な違い:**
- Streamlit を廃止 → FastAPI + 純粋な HTML/CSS/JS に刷新
- データ取得を httpx.AsyncClient による完全非同期化
- SSE（Server-Sent Events）によるリアルタイム進捗表示
- セッション管理をサーバーサイドで一元管理

---

## 2. ファイル構成

```
C:\Users\tarchi\AIBI4\
├── .env                        # 環境変数（SUPABASE_URL, SUPABASE_KEY, OPENAI_API_KEY）
└── v8\
    ├── V8_DEV_GUIDE.md         # 本ドキュメント
    ├── backend\
    │   ├── main.py             # FastAPI アプリ本体・起動エントリポイント
    │   ├── data_router.py      # データ取得エンドポイント（SSE）
    │   ├── analysis_router.py  # 6項目分析エンドポイント
    │   ├── chat_router.py      # LLMチャット・音声入力エンドポイント
    │   ├── analysis_service.py # 6項目分析ロジック（matplotlib グラフ生成）
    │   ├── llm_service.py      # OpenAI 呼び出し・コード実行・ファジー補正
    │   ├── session.py          # インメモリセッション管理（TTL 2時間）
    │   ├── requirements.txt    # Python 依存パッケージ
    │   ├── .env.example        # 環境変数テンプレート
    │   ├── Dockerfile          # Railway デプロイ用（未検証）
    │   └── railway.toml        # Railway 設定（未検証）
    └── frontend\
        ├── index.html          # メイン HTML
        ├── css\
        │   └── style.css       # 全スタイル（ライトモード）
        └── js\
            ├── app.js          # メインアプリロジック
            ├── api.js          # バックエンド API ラッパー
            └── voice.js        # 音声録音（MediaRecorder）
```

---

## 3. 環境構築・起動手順

### 3-1. 初回セットアップ

```bash
# プロジェクトディレクトリに移動
cd C:\Users\tarchi\AIBI4\v8\backend

# 仮想環境の作成（初回のみ）
python -m venv .venv

# 仮想環境の有効化
.venv\Scripts\activate

# パッケージのインストール
pip install -r requirements.txt
```

### 3-2. 毎回の起動手順

```bash
# 1. 仮想環境の有効化
cd C:\Users\tarchi\AIBI4\v8\backend
.venv\Scripts\activate

# 2. uvicorn 起動（--reload は開発時のみ）
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 3. ブラウザでアクセス
# http://localhost:8000
```

> **注意:** `uvicorn` コマンドは仮想環境が有効化されていないと "認識されていません" エラーになる。
> 必ず `python -m uvicorn` の形式で実行すること。

### 3-3. 環境変数

`.env` は `C:\Users\tarchi\AIBI4\.env` に配置（`main.py` が自動ロード）。

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4.1-mini-2025-04-14
```

### 3-4. 動作確認

```bash
# ヘルスチェック（ブラウザ or curl）
curl http://localhost:8000/api/health
# → {"status":"ok","version":"8.0.0"}
```

---

## 4. アーキテクチャ詳細

### 4-1. データ取得フロー

```
[フロントエンド]
  onFetchClick()
    → POST /api/fetch（SSE接続）
        ↓
[バックエンド: data_router.py]
  1. 月ごとに3日単位チャンク分割（CHUNK_DAYS=3）
  2. asyncio.Semaphore(2) で最大2並列フェッチ
  3. httpx.AsyncClient → Supabase RPC get_izakaya_sales
     - ページネーション: ?limit=1000&offset=N（Rangeヘッダー不可）
     - リトライ: 502/503/504 は最大3回・指数バックオフ
  4. チャンク完了ごとに SSE で進捗イベントを送信
  5. 全チャンク完了後:
     - run_in_executor で _build_df() → DataFrame 整形
     - run_in_executor で build_data_summary() → LLM サマリー生成
  6. セッションに df・summary_text を保存
  7. SSE done イベントを送信
```

### 4-2. チャンク分割の仕様

- **単位**: 月ごとに独立して分割（例: 2025-09 と 2025-11 を選択しても 2025-10 のチャンクは生成しない）
- **理由**: 連続日付範囲で分割すると、選択していない月のチャンクが大量生成される問題を回避

### 4-3. セッション管理

- `session.py` がインメモリで管理（サーバー再起動でリセット）
- TTL = 2時間（期限切れは次回セッション作成時に自動削除）
- 保存内容: `df`（DataFrame）、`summary_text`（LLMサマリー）、`chat_history`（会話履歴）

### 4-4. 6項目分析（analysis_service.py）

| 分析番号 | 内容 |
|---------|------|
| ① | 日別売上推移 |
| ② | 時間帯別来客数 |
| ③ | 店舗別売上比較 |
| ④ | 客単価分布 |
| ⑤ | 商品カテゴリ別売上（ドリンク/ヘビー/ライト） |
| ⑥ | 客層別分析 |

グラフは base64 PNG として返却。インサイトテキストも合わせて返す。

### 4-5. チャット分析（llm_service.py）

- モデル: `gpt-4.1-mini-2025-04-14`（環境変数で変更可）
- ファジー補正: 店舗名・商品名の表記ゆれを自動修正してからLLMに渡す
- LLM生成コード: `exec()` で実行 → matplotlib グラフ生成
- コードサニタイズ: `import` 削除、`.append()` → `pd.concat()` 変換

---

## 5. APIエンドポイント一覧

| メソッド | パス | 説明 |
|---------|------|------|
| GET | `/api/health` | ヘルスチェック |
| GET | `/api/months` | 利用可能な月一覧（Supabase visits テーブルから取得）|
| GET | `/api/stores` | 店舗一覧（store_id, store_name）|
| POST | `/api/sessions` | セッション作成 → `{session_id}` を返す |
| POST | `/api/fetch` | データ取得（SSE ストリーミング）|
| GET | `/api/sessions/{sid}/summary` | 取得済みデータのサマリー |
| POST | `/api/analysis/{sid}` | 6項目分析実行 |
| POST | `/api/chat/{sid}` | LLM チャット |
| DELETE | `/api/chat/{sid}` | チャット履歴クリア |
| POST | `/api/voice/{sid}` | 音声 → テキスト（Whisper）|

### SSE イベント形式（`/api/fetch`）

```json
{"type": "progress", "done": 5, "total": 42, "rows": 3200, "pct": 12, "month": "2025-09"}
{"type": "processing", "message": "データを整形中…"}
{"type": "processing", "message": "LLM サマリーを生成中…"}
{"type": "done", "rows": 28000, "columns": ["伝票番号", "店舗名", ...]}
{"type": "error", "message": "2025-09-28〜2025-09-30: ..."}
```

---

## 6. 重要な実装上の注意点（バグ修正履歴）

### ❶ main.py: ルーター登録順序（最重要）

```python
# NG: StaticFiles を先に mount するとすべてのルートが静的配信に吸収される
app.mount("/", StaticFiles(...))  # ← これより先にルーターを登録しないといけない

# OK: ルーター → StaticFiles の順番を厳守
app.get("/api/health")  # まずヘルスチェック
app.include_router(data_router, prefix="/api")
app.include_router(analysis_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.mount("/", StaticFiles(...))  # 最後
```

### ❷ main.py: Windows MIMEタイプ問題

```python
# Windows のレジストリが .js を text/plain にマッピングする場合がある
# → ブラウザが ES Modules を拒否する
import mimetypes
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("text/html", ".html")
```

### ❸ data_router.py: PostgREST ページネーション

```python
# NG: Range ヘッダーは POST RPC では無視される → 常に先頭1000件しか返らない
headers={"Range": "0-999"}  # 効果なし

# OK: クエリパラメータで制御
resp = await client.post(
    f"{SUPABASE_URL}/rest/v1/rpc/get_izakaya_sales",
    params={"limit": RPC_PAGE_SIZE, "offset": offset},  # ← これが正解
    json=params,
)
```

### ❹ data_router.py: 非同期パターン

```python
# NG: concurrent.futures.as_completed() はイベントループをブロックする
# NG: asyncio.gather() はエラー時に全タスクがキャンセルされる

# OK: asyncio.wait(FIRST_COMPLETED) + Semaphore の組み合わせ
task_map = {asyncio.create_task(fetch_one(cs, ce)): (cs, ce) for cs, ce in chunks}
pending = set(task_map.keys())
while pending:
    finished, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
    for task in finished:
        ...
```

### ❺ api.js: エラーイベントの扱い

```javascript
// NG: チャンクエラーで reject() するとフェッチ全体が中断される
if (ev.type === "error") reject(new Error(ev.message));  // NG

// OK: 個別エラーは警告のみ（他チャンクは継続）
if (ev.type === "error") console.warn("chunk error:", ev.message);  // OK
```

### ❻ requirements.txt: httpx バージョン制約

```
# supabase==2.10.0 が httpx<0.28 を要求するため上限を設ける
httpx>=0.26,<0.28
```

### ❼ 日本語フォント（analysis_service.py / llm_service.py 両方）

```python
import platform
if platform.system() == "Windows":
    plt.rcParams["font.family"] = ["Yu Gothic", "Meiryo", "MS Gothic", "DejaVu Sans"]
else:
    plt.rcParams["font.family"] = ["Noto Sans CJK JP", "IPAGothic", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
```

### ❽ llm_service.py: exec_graph_code の DataFrame 参照（2026-06 修正）

```python
# NG: df を直接渡すとLLMコードが df に列追加→セッション上の df が汚染される
safe_globals = {"df": df}  # NG

# OK: コピーを渡す
safe_globals = {"df": df.copy()}  # OK（セッションの df を変更しない）
```

### ❾ llm_service.py: print() 出力キャプチャ（2026-06 追加）

LLMが生成したコード内の `print()` は集計結果（ランキング等）の表示に使う。
`sys.stdout` をグローバルに差し替えると並列リクエスト時に干渉するため、
`safe_globals` にカスタム `print` 関数を注入してスレッドセーフにキャプチャする。

```python
output_lines: list[str] = []

def _captured_print(*args, **kwargs):
    sep = kwargs.get("sep", " ")
    end = kwargs.get("end", "\n")
    output_lines.append(sep.join(str(a) for a in args) + end)

safe_globals = {
    "pd": pd, "np": np, "plt": plt, "matplotlib": matplotlib,
    "df": df.copy(), "print": _captured_print,  # ← ここでカスタム print を注入
}
```

`text_output = "".join(output_lines).strip()` で取り出し、`chat_router.py` 側で
LLM のテキスト回答末尾に追記して `combined_text` として返す。

### ❿ llm_service.py: _fig_has_content の texts チェック（2026-06 修正）

```python
# NG: ax.text() で「データなし」を描いても空判定になりエラーカード表示
#    → ax.texts は patches/lines/collections 等と別扱い

# OK: ax.texts チェックを追加
if (getattr(ax, "texts", None) and len(ax.texts) > 0):
    return True
```

`ax.texts` は `ax.text()` / `ax.annotate()` で明示的に追加した Text オブジェクトのみを含む
（タイトル・軸ラベルは含まない）ため、誤検知なし。

### ⓫ llm_service.py: システムプロンプトの質問分類（2026-06 修正）

「を教えて」を"グラフ不要な一覧確認"の例示にしていたため、
「お勧め商品を教えて」のようなランキング質問が誤って一覧系と判定されていた。

```
# 修正前（問題あり）
■ グラフ不要な質問: 「〜を教えて」など

# 修正後
■ グラフ不要な質問: 「どんな商品がありますか」「店舗一覧を見せて」など単純な列挙確認のみ
※「お勧め」「人気」「ランキング」「売れ筋」「上位」「比較」「分析」を含む質問は
  たとえ「〜を教えて」という形でも必ず集計・グラフを行うこと
```

ランキング系質問では「1つのコードブロックに print() + グラフをまとめる」方式を明示。

---

## 7. フロントエンド構成

### 画面レイアウト

```
┌─────────────────────────────────────────────────────────┐
│ サイドバー (320px)        │ メインエリア                    │
│                           │                               │
│ ヘッダー (🍺 AIBI4 v8.1) │ [空の状態]                     │
│ ─────────────────────    │   or                          │
│ 📅 分析期間 (月チップ)    │ [データ取得中] ← 進捗パネル     │
│ 🏪 店舗フィルタ           │   or                          │
│ 🔄 データを取得するボタン │ [読込済]                        │
│ ─────────────────────    │   データ情報バー                │
│ 🧠 分析チャット           │   KPI カード                   │
│   ユーザー質問履歴        │   タブ [ベース分析 / チャット]  │
│   テキストボックス        │     ベース分析: 6枚グラフカード │
│   [🎤] [送信]            │     チャット: 質問+回答+グラフ  │
└─────────────────────────────────────────────────────────┘
```

### チャット分析の表示仕様

チャットで質問すると、メインエリアの「チャット分析」タブに以下の構成でカードが追加される：

```
┌─────────────────────────────────────────┐
│ Q: ユーザーの質問テキスト（青ボーダー） │
│ LLM の回答テキスト                      │
│ ┌──────────────┬──────────────┐         │
│ │  グラフ①    │  グラフ②    │         │
│ └──────────────┴──────────────┘         │
└─────────────────────────────────────────┘
```

サイドバーはユーザーの質問履歴と「分析中…」スピナーのみ表示（LLM回答テキストはメインエリアに表示）。

### 主要 CSS 変数

```css
--bg:       #eef0f7   /* ページ背景 */
--surface:  #ffffff   /* カード背景 */
--accent:   #3b6ee8   /* メインカラー（青）*/
--accent2:  #6c42f0   /* サブカラー（紫）*/
--success:  #1a9c52
--danger:   #c0392b
--sidebar-w: 320px
```

---

## 8. 今後の開発課題

### 完了済み
- [x] **Railway デプロイ**: 本番稼働中（`Dockerfile` + `railway.toml`）
- [x] **チャット回答の品質改善**: print() キャプチャ・ランキング質問の分類修正（2026-06）

### 検討中
- [ ] **セッションの永続化**: 現在はインメモリのみ。サーバー再起動でデータが消える
- [ ] **複数ユーザー対応**: セッションはすでに UUID 管理だが、本格運用時はデータ量に注意

### 既知の無害なログ
uvicorn コンソールに以下が出ることがあるが、動作に影響なし：
```
SettingWithCopyWarning: A value is trying to be set on a copy of a slice from a DataFrame
FigureCanvasAgg is non-interactive, and thus cannot be shown
```

---

## Supabase データベース構成（参考）

| テーブル | 件数（概算）| 備考 |
|---------|-----------|------|
| stores | 27店舗 | latitude/longitude 含む |
| visits | 939件 | 来店記録 |
| orders | - | 注文ヘッダー |
| order_items | 282,983件 | 注文明細 |
| weather_locations | 21地点 | 天気観測地点 |
| daily_weather | 8,946件 | 気象データ |

**使用 RPC:**
```sql
get_izakaya_sales(p_start_date, p_end_date, p_store_ids[])
-- SECURITY DEFINER
-- 売上データ + 天気データを LEFT JOIN して返す
-- PostgRESTのRange ヘッダーは POST RPC では無効
-- → クエリパラメータ ?limit=N&offset=N で制御すること
```
