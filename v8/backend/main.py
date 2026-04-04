"""
AIBI4 V8 — FastAPI バックエンド
起動: uvicorn main:app --host 0.0.0.0 --port 8000
"""
import mimetypes
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Windows では .js が text/plain になる場合があるため明示的に上書き
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("text/html", ".html")

# ── 環境変数ロード ──
_env_path = Path(__file__).parent.parent.parent / ".env"  # C:\Users\tarchi\AIBI4\.env
load_dotenv(dotenv_path=_env_path, override=False)
load_dotenv(dotenv_path=Path(__file__).parent / ".env", override=False)

app = FastAPI(title="AIBI4 V8", version="8.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── ヘルスチェック（StaticFiles mount より先に登録）──
@app.get("/api/health")
def health():
    return {"status": "ok", "version": "8.0.0"}

# ── ルーター登録（StaticFiles mount より先に登録）──
from data_router import router as data_router
from analysis_router import router as analysis_router
from chat_router import router as chat_router

app.include_router(data_router,     prefix="/api")
app.include_router(analysis_router, prefix="/api")
app.include_router(chat_router,     prefix="/api")

# ── フロントエンド静的ファイル配信（最後に登録）──
frontend_path = Path(__file__).parent.parent / "frontend"
if frontend_path.exists():
    app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="frontend")
