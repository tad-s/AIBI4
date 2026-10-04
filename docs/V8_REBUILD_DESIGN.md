# AIBI4 V8 再構築デザイン案

作成日: 2026-07-08

## 1. 前提

現行 v8 は v7 の Streamlit 画面を FastAPI + HTML/JS に移植した性格が強く、実用BIとしては以下が弱い。

- 左ペイン中心の「期間・店舗を選んで分析する」単一業務フローに寄りすぎている
- AI がチャット欄に閉じており、データ準備・モデル設計・レポート・アラート・アクションに横断していない
- 取り込みデータの信頼性、意味定義、権限、監査ログが UI の主役になっていない
- 画面内の日本語文字化けがあり、現行UIを継ぎ足すより刷新した方が速い

したがって、再構築案では「グラフを出すアプリ」ではなく、**データ接続 → セマンティック設計 → AI探索 → レポート化 → 自動監視・実行**まで扱う AI連動型BIプラットフォームとして設計する。

## 2. 参考にした現在のBIトレンド

- Power BI Copilot: レポート内ペイン、独立した全画面AI、アプリ内AIなど複数サーフェスでチャット・要約・レポート作成・DAX支援を提供する方向
- Tableau Next / Pulse: trusted semantics、metric layer、proactive insights、Slack/Teams/email/mobile など業務導線内への配信
- Sigma AI: warehouse-native、AI回答のロジック/式/フィルタを検証可能、スプレッドシートUX、AI Apps/Agents、権限継承
- ThoughtSpot Spotter: search/agent型分析、モデル準備、用語定義、参照質問、チャット履歴、Slack連携、アラート/監視

共通項は、単なる自然言語チャットではなく、**信頼できる意味定義・説明可能性・業務アクション・ガバナンス**が中心になっている点。

## 3. 新しいプロダクトコンセプト

### AIBI Nexus

自然言語で質問できるだけでなく、AI がデータの状態・意味定義・分析根拠・次アクションまで継続的に管理する BI ワークスペース。

### UX の柱

1. **AI First, Chat Only ではない**
   - 全画面に共通AIサイドパネルを置く
   - 取り込み、項目設計、探索、レポート、アラート設定の各作業をAIが補助する

2. **信頼性をUIに出す**
   - 回答には信頼度、使用データ、集計条件、生成SQL/式、更新時刻を表示
   - 「なぜそう言えるか」を確認できる

3. **セマンティックレイヤーを中心にする**
   - 売上、粗利、客数、MRRなどの指標定義を明示
   - 同義語、非表示列、PII、RLS、結合関係を画面で管理

4. **Proactive Insights**
   - ユーザーが聞く前に異常値、前年差、ドライバー、欠損、同期失敗を通知
   - Slack/メール/Teams/Webhook 連携を前提にする

5. **Explore → Report → Action**
   - その場で探索し、カード化し、レポートに保存し、アラート/ワークフローに昇格できる

## 4. 情報設計

| 画面 | 目的 | 主なUI |
|---|---|---|
| Home | 経営/現場が毎日見る入口 | KPI、AI要約、変化点、アクションキュー |
| Ask AI | 自然言語探索 | チャット、回答カード、根拠、SQL/式、引用データ |
| Data Hub | データ接続・同期 | SaaS/API/DB/ファイル/OCR、同期状態、品質スコア |
| Model | データ設計・意味定義 | 項目選択、表示名編集、型、PII、指標定義、結合 |
| Explore | アドホック分析 | ピボット/表計算型グリッド、チャートビルダー |
| Reports | 共有・配信 | ダッシュボード、レポート、スケジュール、埋め込み |
| Automations | 監視・実行 | 異常検知、しきい値、Slack通知、Webhook、承認 |
| Governance | 運用管理 | 権限、監査ログ、リネージ、データ品質、コスト |

## 5. 再構築時に捨てるもの

- 「店舗・月選択が最初に必須」という画面構造
- matplotlib画像を中心にした固定6分析の見せ方
- チャット欄と分析結果欄が分離しただけのAI UX
- インメモリセッション前提の状態管理
- CSV/PDF/画像を単なるアップロード枠として扱う設計

## 6. MVP 実装順

1. **App Shell**
   - 左ナビ、上部検索、右AIパネル、ページルーティング
   - 既存 `frontend` は置換候補。まずモックを実装して画面仕様を確定する

2. **Data Hub**
   - コネクタ一覧、接続ウィザード、ファイル取り込み、同期ジョブ状態
   - 既存 Supabase 取得APIは「データソースの1つ」として扱う

3. **Model**
   - 取り込み項目の選択、名称編集、型変更、メモ、PII、同義語、指標定義
   - AI回答の精度はここがボトルネックになるため最優先

4. **Ask AI**
   - 回答本文、可視化、使用データ、生成SQL、信頼度、再実行、レポート保存
   - LLM出力をそのまま表示せず、必ず構造化レスポンスにする

5. **Home / Reports / Automations**
   - 日次の変化点、レポート保存、アラート配信、Slack/メール連携

6. **Governance**
   - RLS、PIIマスク、監査ログ、コスト、利用状況

## 7. 技術方針

### フロントエンド

- 実運用では Vanilla JS から React/TypeScript + TanStack Query + Zustand 等へ移行推奨
- 大量表・フィールド設計には仮想スクロールが必要
- チャートは画像生成ではなく ECharts / Vega-Lite / Plotly 等のクライアント描画に寄せる

### バックエンド

- FastAPI は継続可能
- セッションは Redis / DB 永続化
- 接続情報は暗号化保存
- ジョブ実行はバックグラウンドキュー化
- LLM回答は `answer`, `visualization_spec`, `sql`, `confidence`, `lineage`, `warnings`, `suggested_actions` に構造化

### データモデル

- `data_sources`
- `ingestion_jobs`
- `datasets`
- `schema_fields`
- `semantic_metrics`
- `relationships`
- `ai_questions`
- `answer_artifacts`
- `alerts`
- `audit_logs`

## 8. 作成したモック

- `etc/mockup_ai_bi_rebuild.html`

このモックは実装仕様のたたき台であり、現行 v8 の置換対象を決めるための判断材料として使う。
