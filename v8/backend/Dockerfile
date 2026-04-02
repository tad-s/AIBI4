FROM python:3.12-slim

WORKDIR /app/backend

# 日本語フォント（matplotlib 用）
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# バックエンドコード
COPY . .

# フロントエンドを配信できるようにコピー
COPY ../frontend /app/frontend

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
