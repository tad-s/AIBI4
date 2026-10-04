"""AIBI4 v12 — AIネイティブBI バックエンド（FastAPI + DuckDB）。"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from core.config import settings
from routers import ask, data, meta, query

app = FastAPI(title="AIBI4 v12 API", version="12.0.0")

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


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "12.0.0"}


frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
