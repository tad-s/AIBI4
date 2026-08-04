"""T1 — テング酒場池袋東口店 レコメンドPoC専用BI."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from routers.api import router as api_router

app = FastAPI(title="AIBI4 T1 PoC", version="1.0.0")
app.include_router(api_router)

frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
