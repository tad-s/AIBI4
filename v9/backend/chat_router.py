"""
chat_router.py — V9 chat / voice endpoints.

V9 changes:
- Supports clarification-first conversations for ambiguous analysis requests.
- Stores chat analysis outputs for Excel export.
- Stores evidence log entries for Q&A, generated graphs, and execution status.
"""
from datetime import datetime, timezone
import re

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

import session as sess
from llm_service import (
    build_fuzzy_context,
    call_llm_chat,
    exec_graph_code,
    parse_llm_response,
    transcribe_audio,
)

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    new_chat: bool = False


_AMBIGUOUS_PATTERNS = re.compile(
    r"(売れ筋|構成|分析|傾向|比較|見たい|知りたい|おすすめ|伸ばしたい|改善|良い感じ|ざっくり)"
)
_METRIC_PATTERNS = re.compile(r"(売上|数量|件数|客単価|注文数|商品数|構成比|前年比|時間帯|店舗|商品別|月別)")
_IMPOSSIBLE_PATTERNS = re.compile(r"(年齢|性別|個人|会員|リピート|再来店|職業|住所|電話|メール)")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_evidence(sid: str, entry: dict) -> None:
    s = sess.get_session(sid)
    if not s:
        return
    evidence = list(s.get("evidence_log") or [])
    evidence.append({"ts": _now_iso(), **entry})
    sess.update_session(sid, evidence_log=evidence)


def _needs_clarification(message: str, pending: dict | None) -> tuple[bool, str]:
    if pending:
        return False, ""
    msg = message.strip()
    if _IMPOSSIBLE_PATTERNS.search(msg):
        return True, (
            "その分析は現在のデータ項目だけでは直接実行できません。"
            "現在使える主な軸は、店舗・商品・注文日時/来店時間・人数・客単価・数量・天気です。"
            "代替として、店舗別/商品別/時間帯別/客単価別の分析にしますか？"
        )
    if _AMBIGUOUS_PATTERNS.search(msg) and not _METRIC_PATTERNS.search(msg):
        return True, (
            "分析の切り口を確認させてください。"
            "何を基準に見ますか？ 例: ①売上金額 ②注文数量 ③客単価への影響 ④時間帯別 ⑤店舗別。"
            "対象店舗や商品があれば併せて指定してください。"
        )
    return False, ""


@router.post("/chat/{sid}")
async def chat(sid: str, req: ChatRequest):
    s = sess.get_session(sid)
    if not s:
        raise HTTPException(status_code=404, detail="セッションが見つかりません。")
    df = s.get("df")
    if df is None:
        raise HTTPException(status_code=400, detail="データが取得されていません。")

    summary_text = s.get("summary_text", "")
    chat_history: list[dict] = [] if req.new_chat else list(s.get("chat_history") or [])
    pending = None if req.new_chat else s.get("pending_analysis")

    needs_clarify, clarify_text = _needs_clarification(req.message, pending)
    if needs_clarify:
        pending_analysis = {"original_request": req.message, "created_at": _now_iso()}
        chat_history.append({"role": "user", "content": req.message})
        chat_history.append({"role": "assistant", "content": clarify_text})
        sess.update_session(sid, chat_history=chat_history, pending_analysis=pending_analysis)
        _append_evidence(sid, {
            "type": "chat_clarification",
            "question": req.message,
            "answer": clarify_text,
            "status": "clarification_needed",
            "data_rows": int(len(df)),
            "data_columns": list(map(str, df.columns)),
        })
        return {"text": clarify_text, "graphs": [], "raw": clarify_text, "clarification_needed": True}

    effective_message = req.message
    if pending:
        effective_message = (
            "前回の分析依頼: " + str(pending.get("original_request", "")) + "\n"
            "今回の補足回答: " + req.message + "\n"
            "上記を統合して、ユーザーが本来見たい分析を実行してください。"
        )
        sess.update_session(sid, pending_analysis=None)

    patched_msg, extra_system = build_fuzzy_context(df, effective_message)
    chat_history.append({"role": "user", "content": patched_msg})

    raw_response = await run_in_threadpool(call_llm_chat, summary_text, chat_history, extra_system)
    chat_history.append({"role": "assistant", "content": raw_response})
    sess.update_session(sid, chat_history=chat_history, pending_analysis=None)

    text_part, code_blocks = parse_llm_response(raw_response)

    graphs = []
    extra_texts: list[str] = []
    graph_errors: list[str] = []
    for code in code_blocks:
        result = await run_in_threadpool(exec_graph_code, code, df)
        graphs.append(result)
        if result.get("text_output"):
            extra_texts.append(result["text_output"])
        if not result.get("ok", True):
            graph_errors.append(str(result.get("error") or "graph execution error"))

    combined_text = text_part
    if extra_texts:
        combined_text = (text_part + "\n\n" + "\n\n".join(extra_texts)).strip()

    chat_analyses = list(s.get("chat_analyses") or [])
    chat_analyses.append({
        "question": req.message,
        "effective_message": effective_message,
        "new_chat": bool(req.new_chat),
        "text": combined_text,
        "graphs": [g for g in graphs if g.get("image_b64")],
    })
    sess.update_session(sid, chat_analyses=chat_analyses)

    _append_evidence(sid, {
        "type": "chat_analysis",
        "question": req.message,
        "new_chat": bool(req.new_chat),
        "effective_message": effective_message,
        "answer_excerpt": combined_text[:1200],
        "code_blocks": len(code_blocks),
        "graph_count": len([g for g in graphs if g.get("image_b64")]),
        "graph_errors": graph_errors,
        "status": "ok" if not graph_errors else "partial_error",
        "data_rows": int(len(df)),
        "data_columns": list(map(str, df.columns)),
        "evidence_note": "Generated graphs were produced by executing LLM code against the in-memory df. File reads are blocked by sanitize_code().",
    })

    return {"text": combined_text, "graphs": graphs, "raw": raw_response, "clarification_needed": False}


@router.post("/voice/{sid}")
async def voice_to_text(sid: str, audio: UploadFile = File(...)):
    s = sess.get_session(sid)
    if not s:
        raise HTTPException(status_code=404, detail="セッションが見つかりません。")
    audio_bytes = await audio.read()
    filename = audio.filename or "audio.webm"
    try:
        text = await run_in_threadpool(transcribe_audio, audio_bytes, filename)
        return {"text": text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"音声変換エラー: {e}")


@router.delete("/chat/{sid}")
def clear_chat(sid: str):
    s = sess.get_session(sid)
    if not s:
        raise HTTPException(status_code=404, detail="セッションが見つかりません。")
    sess.update_session(sid, chat_history=[], chat_analyses=[], pending_analysis=None)
    _append_evidence(sid, {"type": "chat_clear", "status": "ok"})
    return {"ok": True}
