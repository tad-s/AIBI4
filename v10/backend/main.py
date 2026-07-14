"""AIBI4 v10 — AIネイティブBI バックエンド（FastAPI + DuckDB）。"""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from core.config import settings
from routers import analyses_router, ask, data, meta, query

app = FastAPI(title="AIBI4 v10 API", version="10.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN, "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(meta.router)
app.include_router(data.router)
app.include_router(query.router)
app.include_router(ask.router)
app.include_router(analyses_router.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "10.0.0"}


# 本番: ビルド済みフロント（frontend/dist）が存在すれば静的配信する。
# API ルートは上で登録済みのため、"/" マウントは残りのパスのみ処理する。
_dist = os.getenv("FRONTEND_DIST") or os.path.join(
    os.path.dirname(__file__), "..", "frontend", "dist"
)
if os.path.isdir(_dist):
    app.mount("/", StaticFiles(directory=_dist, html=True), name="static")
