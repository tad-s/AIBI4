"""
session.py — インメモリセッション管理
セッションID (UUID) ごとに DataFrame・チャット履歴を保持する。
2時間経過したセッションは自動削除。
"""
import time
import uuid
from typing import Optional
import pandas as pd

_sessions: dict[str, dict] = {}
_TTL = 7200  # 2時間


def _cleanup():
    now = time.time()
    expired = [k for k, v in _sessions.items() if now - v["created_at"] > _TTL]
    for k in expired:
        del _sessions[k]


def create_session() -> str:
    _cleanup()
    sid = str(uuid.uuid4())
    _sessions[sid] = {
        "created_at": time.time(),
        "df": None,
        "summary_text": None,
        "chat_history": [],
    }
    return sid


def get_session(sid: str) -> Optional[dict]:
    return _sessions.get(sid)


def update_session(sid: str, **kwargs):
    if sid in _sessions:
        _sessions[sid].update(kwargs)


def get_df(sid: str) -> Optional[pd.DataFrame]:
    s = _sessions.get(sid)
    return s["df"] if s else None
