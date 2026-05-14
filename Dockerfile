# AIBI4 V8 — Railway デプロイ用 Dockerfile
FROM python:3.12-slim

WORKDIR /app

# ── 日本語フォント（matplotlib グラフ用）──
RUN apt-get update && apt-get install -y --no-install-recommends \
        fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

# ── Python 依存関係（レイヤーキャッシュ効率のため先にインストール）──
COPY v8/backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# ── matplotlib フォントキャッシュをクリア（インストールしたフォントを認識させる）──
RUN python -c "import shutil, matplotlib; shutil.rmtree(matplotlib.get_cachedir(), ignore_errors=True)"

# ── アプリケーションファイル ──
COPY v8/backend/ ./backend/
COPY v8/frontend/ ./frontend/

WORKDIR /app/backend

ENV PYTHONUNBUFFERED=1
ENV MPLBACKEND=Agg

# Railway は $PORT を自動設定する（ローカルは 8000）
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
