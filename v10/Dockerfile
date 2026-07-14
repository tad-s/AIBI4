# ── stage 1: フロントエンド（React + Vite）をビルド ──
FROM node:22-alpine AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ── stage 2: バックエンド（FastAPI + DuckDB）＋静的配信 ──
FROM python:3.13-slim
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=frontend /fe/dist ./frontend_dist
ENV FRONTEND_DIST=/app/frontend_dist
EXPOSE 8000
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
