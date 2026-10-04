# AIBI4 v12 再構築ブループリント

作成日: 2026-07-08

## 1. 結論

V8/V9は「既存分析を画面に出すツール」としては有効だが、実用に耐えるAI連動型BIツールとしては、継ぎ足しでは限界がある。

今後はV8/V9を保守版として残し、v12を本命の再構築版として進める。

v12の設計思想は以下。

- AIチャットを付けたBIではなく、AIがデータ接続・意味定義・探索・説明・レポート化・監視まで支援するBIにする。
- LLMに自由なPythonコードを書かせず、必ず構造化された分析仕様を生成させる。
- グラフ画像中心ではなく、再利用可能なチャート仕様・集計結果・根拠ログを保存する。
- UIは「月と店舗を選んで分析実行」から、「ワークスペース内でデータを理解し、問い、保存し、監視する」形に変える。

## 2. 参考にしたBI/AI UXの要点

### Power BI Copilot

MicrosoftのPower BI Copilotは、レポート右側のCopilotペイン、独立した全画面Copilot、アプリ内Copilotなど複数のAIサーフェスを提供している。また、AIが正しく答えるにはセマンティックモデルの準備が重要であり、トピック変更時はチャット履歴をクリアして前文脈を断つ運用が推奨されている。

v12への反映:

- 右AIパネルと全画面Ask AIを分ける。
- セマンティックモデル管理を主要画面に昇格する。
- 継続チャットと新規チャットを明確に分ける。

### ThoughtSpot Spotter

ThoughtSpot Spotterは、AIアナリストとして自然言語分析、ガバナンス、セキュリティ、データモデル文脈、複数データソースの選択、外部ツール連携を重視している。

v12への反映:

- 自然言語回答に必ず「使用データ・集計式・フィルタ・SQL・信頼度」を付ける。
- データモデルに業務用語・同義語・非推奨項目を持たせる。
- 将来的にSlack/Teams/メール/Webhookへ通知・アクション連携できる構造にする。

## 3. 現行実装の評価

### 残すもの

- FastAPIベースのAPI構成
- Supabaseからのデータ取得ロジック
- RailwayでV8/V9を独立運用した経験
- 音声入力
- Excel出力
- エビデンスログの考え方
- v12で既に作り始めているセマンティック層とDuckDB実行層

### 捨てるもの

- matplotlib画像を中心にした固定グラフ生成
- LLMにPythonコードを書かせて `exec` する設計
- インメモリセッション前提の長期利用
- 月・店舗選択が最初に必須の画面構造
- 「ベース分析を全部出す」だけの画面
- データセット固有の分岐がアプリ各所に散る設計
- 文字化けを起こしやすいファイル・エンコード運用

## 4. 新しいプロダクト像

名称案: AIBI Nexus

飲食・小売などの業務データを、現場担当者でも自然言語で探索でき、分析結果の根拠まで確認できるAIネイティブBIワークスペース。

### 利用者別の主目的

| 利用者 | 目的 | 主要画面 |
|---|---|---|
| 経営/マネージャー | KPI変化と打ち手を素早く把握 | Home, Reports, Alerts |
| 店舗/エリア担当 | 店舗別・時間帯別・商品別の改善点を把握 | Ask AI, Explore |
| 分析担当 | 指標定義、軸設計、深掘り分析 | Model, Explore |
| 管理者 | データ接続、権限、監査、品質管理 | Data Hub, Governance |

## 5. UI/UX再設計

### 5-1. 全体レイアウト

```
┌────────────────────────────────────────────────────────────┐
│ Top Bar: データセット / 検索 / 期間 / 更新状態 / 共有       │
├───────┬───────────────────────────────────────┬────────────┤
│ Nav   │ Main Workspace                         │ AI Panel   │
│       │                                       │            │
│ Home  │ ページごとのキャンバス                 │ 質問       │
│ Ask   │ KPI / グラフ / 表 / レポート           │ 根拠       │
│ Data  │                                       │ 次アクション│
│ Model │                                       │            │
│ Explore│                                      │            │
│ Reports│                                      │            │
│ Alerts │                                      │            │
└───────┴───────────────────────────────────────┴────────────┘
```

### 5-2. 主要画面

#### Home

- 今日見るべきKPI
- AIによる変化点サマリー
- 売上/客単価/注文数/販売点数のトレンド
- 異常値・未確認アラート
- 最近保存した分析
- 次に見るべき質問候補

#### Ask AI

- 自然言語で質問
- 回答カード
- グラフ
- 使用データ
- 適用フィルタ
- 生成SQL
- 信頼度
- 根拠テーブル
- レポート保存
- Excel/PNG/CSV出力
- 継続チャット/新規チャットの明確な切替

#### Data Hub

- Supabase、CSV/XLSX、将来的にはPOS/API/OES連携
- データ取得ジョブ状態
- 最終更新時刻
- 行数、欠損率、重複、異常値
- データ品質スコア

#### Model

- 指標定義
- 軸定義
- 同義語
- 表示名
- 非表示項目
- PII/機密項目
- 結合関係
- 業務用語辞書
- AIに使わせる/使わせない項目の制御

#### Explore

- ピボット/表計算型グリッド
- ドラッグ&ドロップの軸・指標
- チャートタイプ切替
- ドリルダウン
- クロスフィルタ
- 条件保存

#### Reports

- 分析カードを配置してダッシュボード化
- 共有リンク
- Excel/PDF出力
- 定期配信
- コメント/メモ

#### Alerts / Automations

- 閾値監視
- 前年比/前月比/移動平均からの乖離
- 異常検知
- Slack/Teams/メール/Webhook通知
- 人間承認付きアクション

#### Governance

- ユーザー/ロール
- RLS
- 監査ログ
- LLM利用ログ
- コスト
- データリネージ

## 6. AI設計

### 6-1. LLMにはコードを書かせない

V7/V8/V9では、LLMがPythonコードを生成し、サーバー側で実行する流れがある。これは柔軟だが、本番では危険で、再現性も弱い。

v12では以下に統一する。

1. ユーザー質問
2. LLMが構造化JSONの `QuerySpec` を生成
3. Pydanticで検証
4. セマンティックエンジンがSQLを生成
5. DuckDB/Postgresで実行
6. 結果・SQL・根拠・警告を返す

### 6-2. QuerySpec例

```json
{
  "metric": "revenue",
  "dimensions": ["store", "month"],
  "filters": {
    "months": ["2025-09", "2025-10"],
    "stores": ["新宿店"]
  },
  "chart_type": "line",
  "sort": "dim_asc",
  "limit": 20,
  "title": "新宿店の月別売上"
}
```

### 6-3. 回答レスポンス

```json
{
  "answer": "2025年10月の売上は前月比で増加しています。",
  "visualization_spec": {},
  "sql": "SELECT ...",
  "confidence": 0.86,
  "lineage": {
    "dataset": "izakaya",
    "tables": ["orders", "items"],
    "row_count": 12345
  },
  "warnings": [],
  "suggested_actions": [
    "客単価ではなく販売点数でも確認する",
    "時間帯別に分解する"
  ]
}
```

### 6-4. AIの役割

- 質問の意図理解
- 指標/軸/フィルタの候補提示
- 不可能な分析の説明
- 深掘り質問の提案
- 分析結果の要約
- 異常値の説明候補
- レポートタイトル/コメント作成

AIに任せないもの:

- 最終集計値
- SQLの自由生成
- 権限判断
- データ改変
- 根拠のない断定

## 7. データ/分析基盤

### 7-1. 推奨アーキテクチャ

```
Supabase / CSV / XLSX / API
        ↓
Ingestion Jobs
        ↓
Raw Tables
        ↓
Transform / Validation
        ↓
Analytical Cache: DuckDB or Postgres Materialized Views
        ↓
Semantic Layer
        ↓
Query Engine
        ↓
Ask AI / Explore / Reports / Alerts
```

### 7-2. 永続化すべきテーブル

| テーブル | 用途 |
|---|---|
| `data_sources` | 接続先管理 |
| `ingestion_jobs` | データ取得ジョブ |
| `datasets` | データセット定義 |
| `schema_fields` | カラム定義 |
| `semantic_metrics` | 指標定義 |
| `semantic_dimensions` | 軸定義 |
| `semantic_relationships` | テーブル関係 |
| `business_terms` | 業務用語辞書 |
| `ai_questions` | AI質問履歴 |
| `answer_artifacts` | 回答・グラフ・SQL・根拠 |
| `dashboards` | ダッシュボード |
| `dashboard_cards` | 保存済み分析カード |
| `alerts` | 監視ルール |
| `audit_logs` | 操作・LLM・データアクセス監査 |

## 8. フロントエンド技術方針

現行V8/V9のVanilla JSは小規模なら速いが、本格BI UIには不向き。

v12では以下を推奨する。

- React + TypeScript
- Vite
- TanStack Query
- Zustand または Redux Toolkit
- ECharts または Vega-Lite
- AG Grid または TanStack Table
- Tailwind CSS または CSS Modules
- PlaywrightによるE2E

理由:

- 画面状態が多くなる
- グラフカード/フィルタ/AIパネル/レポート編集をコンポーネント化できる
- 型でAPI契約を守れる
- 将来的なダッシュボード編集に耐える

## 9. バックエンド技術方針

FastAPIは継続する。

追加すべきもの:

- PostgreSQL/Supabaseへのアプリ状態永続化
- RedisまたはDBベースのセッション
- Background job queue
- OpenTelemetry/構造化ログ
- APIレスポンススキーマ固定
- LLM入出力ログ
- 権限/RLS
- キャッシュ制御

## 10. MVPの合格基準

v12 MVPは、以下を満たすまで本番候補にしない。

### データ

- データセット選択ができる
- 月・店舗・カテゴリのフィルタができる
- 取得件数・対象期間・更新時刻が明示される
- 欠損/異常/重複の基本チェックが出る

### Ask AI

- 自然言語から `QuerySpec` を生成する
- 曖昧な質問には確認質問を返す
- データにない質問には理由と代替案を返す
- 回答にSQL・フィルタ・使用行数・信頼度が表示される
- 新規チャットと継続チャットを切り替えられる

### Explore

- 指標と軸を選んで表/棒/折れ線を切り替えられる
- 表の値とグラフの値が一致する
- グラフをレポートに保存できる

### Reports

- 保存済みカードを一覧できる
- Excel出力にグラフ・表・条件・根拠が含まれる

### 運用

- セッションがRailway再起動で消えない
- エラーがユーザー向けに理解できる文章で表示される
- 最低限の監査ログが残る

## 11. 実装ロードマップ

### Phase 0: 現行保全

- V8/V9は既存運用版として凍結
- V12を別サービス/別URLで開発
- `.env` とRailwayサービスを分離

### Phase 1: v12基盤

- React/TypeScriptフロントの新規作成
- App Shell
- Data Hubの最小画面
- セマンティックカタログAPI
- QuerySpec実行API
- ECharts描画

### Phase 2: Ask AI

- 自然言語 → QuerySpec
- 確認質問フロー
- 新規/継続チャット
- 回答カード
- SQL/根拠/信頼度表示
- 音声入力

### Phase 3: Explore / Reports

- 指標/軸ビルダー
- ピボットテーブル
- グラフ保存
- ダッシュボード編集
- Excel/PDF出力

### Phase 4: Production

- セッション永続化
- 認証/権限
- 監査ログ
- ジョブキュー
- アラート
- Slack/Teams/メール通知
- 利用状況/コスト管理

## 12. 最初に作るべき画面

1. App Shell
2. Home
3. Ask AI
4. Explore
5. Model

Data HubとGovernanceは重要だが、最初から作り込みすぎると進捗が遅くなる。まずはSupabaseデータを確実に読める前提で、Ask AIとExploreの実用性を先に検証する。

## 13. 実装上の判断

### v12で採用する

- セマンティックレイヤー
- QuerySpec
- DuckDB分析キャッシュ
- 構造化AIレスポンス
- ECharts/Vega-Lite
- React/TypeScript
- 永続セッション

### v12で採用しない

- LLM生成コードのサーバー実行
- matplotlib画像中心UI
- 画面ごとに個別SQL/RPCを増やす設計
- チャット欄だけをAI機能とする設計
- 使い捨てインメモリセッション

## 14. 次の具体作業

1. `v12/frontend` をReact/TypeScriptで新規作成する。
2. `v12/backend` の既存QuerySpecエンジンをAPIとして固める。
3. Supabase取得 → DuckDB投入 → メタ情報表示を一連で動かす。
4. Ask AI画面で自然言語からQuerySpecを生成してグラフ表示する。
5. 回答カードにSQL・根拠・使用データ・信頼度を出す。

この順であれば、現行V8/V9の欠点を引きずらず、実用BIとしての中核から作り直せる。

## 15. 参考リンク

- Microsoft Learn: Copilot for Power BI overview — https://learn.microsoft.com/en-us/power-bi/create-reports/copilot-introduction
- ThoughtSpot Docs: Spotter — https://docs.thoughtspot.com/cloud/latest/spotter
