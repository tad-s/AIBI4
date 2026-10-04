# AIBI4 V12 起動・テスト手順

V12はV10とは別ディレクトリで独立して動作するAIネイティブBIの再構築版です。

## 1. セットアップ

```powershell
cd C:\Users\tarchi\AIBI4\v12\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 2. 外部接続なしの確認

```powershell
$env:PYTHONPATH="."
python smoke_test.py
```

最後に `ALL GREEN` が表示されれば、DuckDB集計エンジンとセマンティック層は正常です。

## 3. ローカル起動

```powershell
cd C:\Users\tarchi\AIBI4\v12\backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn main:app --host 127.0.0.1 --port 8012 --reload
```

ブラウザで以下を開きます。

```text
http://127.0.0.1:8012/
```

## 4. 最初に触る手順

1. 画面上部の `デモデータで開始` を押す
2. KPIとダッシュボードが表示されることを確認する
3. 左ナビの `Explore` を開く
4. 指標・軸を選んで `分析実行` を押す
5. 右側のAIパネルで質問する

例:

```text
店舗別の売上ランキングを見せて
時間帯別の客単価を見たい
カテゴリ別の販売点数を教えて
```

## 5. Supabase接続を使う場合

`C:\Users\tarchi\AIBI4\v12\backend\.env` を作成します。

```env
SUPABASE_URL=...
SUPABASE_KEY=...
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4.1-mini-2025-04-14
FRONTEND_ORIGIN=http://localhost:5173
```

既存のルート `.env` を使う場合:

```powershell
copy C:\Users\tarchi\AIBI4\.env C:\Users\tarchi\AIBI4\v12\backend\.env
```

その後、画面上部で月を選択して `Supabaseから読込` を押します。

## 6. 現時点で実装済み

- FastAPIによるV12 API
- 静的フロント配信
- デモデータ生成
- Supabase読込
- DuckDB分析キャッシュ
- セマンティック指標/軸カタログ
- ダッシュボードKPI/グラフ
- Explore画面
- Ask AI画面
- QuerySpecによる決定論的集計

## 7. 注意点

- V12は開発初期版です。V8/V9の置換ではありません。
- V10とは別ルートのため、V10側は変更しません。
- AI Askは `OPENAI_API_KEY` がない場合は利用できません。
- デモデータではAI Ask以外の画面操作を外部接続なしで確認できます。
