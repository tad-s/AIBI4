"""アプリ設定（環境変数）。"""
import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")

    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4.1-mini-2025-04-14")

    FRONTEND_ORIGIN: str = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")

    # データ取得
    RPC_PAGE_SIZE: int = 1000
    CHUNK_DAYS: int = 3
    MAX_WORKERS: int = 2
    CHUNK_TIMEOUT: float = 120.0

    # セッション
    SESSION_TTL_SEC: int = 7200  # 2時間


settings = Settings()
