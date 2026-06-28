"""
chat_router.py — チャット・音声入力エンドポイント
POST /api/chat/{sid}         LLM チャット（継続チャット対応・あいまい要求は確認メッセージを返す）
POST /api/voice/{sid}        音声 → テキスト（Whisper）
DELETE /api/chat/{sid}       チャット履歴クリア
"""
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

# あいまい/不可能リクエスト判定パターン
_AMBIGUOUS_PATTERNS = re.compile(
    r"(売れ筋|構成|分析|傾向|比較|見たい|知りたい|おすすめ|伸ばしたい|改善|良い感じ|ざっくり)"
)
_METRIC_PATTERNS = re.compile(
    r"(売上|数量|件数|客単価|注文数|商品数|構成比|前年比|時間帯|店舗|商品別|月別)"
)
_IMPOSSIBLE_PATTERNS = re.compile(
    r"(年齢|性別|個人|会員|リピート|再来店|職業|住所|電話|メール)"
)


class ChatRequest(BaseModel):
    message: str
    new_chat: bool = False


def _needs_clarification(message: str, pending: dict | None) -> tuple[bool, str]:
    """あいまいなリクエストや不可能なリクエストの場合 (True, 確認テキスト) を返す。
    すでに pending があるとき（ユーザーが補足回答を送ってきた）はスキップ。"""
    if pending:
        return False, ""
    msg = message.strip()
    if _IMPOSSIBLE_PATTERNS.search(msg):
        return True, (
            "その分析は現在のデータ項目だけでは直接実行できません。\n"
            "現在使える主な軸は、**店舗・商品・注文日時/来店時間・人数・客単価・数量・天気**です。\n"
            "代替として、店舗別/商品別/時間帯別/客単価別の分析にしますか？"
        )
    if _AMBIGUOUS_PATTERNS.search(msg) and not _METRIC_PATTERNS.search(msg):
        return True, (
            "分析の切り口を確認させてください。\n"
            "何を基準に見ますか？\n"
            "例: ①売上金額 ②注文数量 ③客単価への影響 ④時間帯別 ⑤店舗別\n"
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
    # new_chat=True のときは会話履歴・pending をリセットして新規開始
    chat_history: list[dict] = [] if req.new_chat else list(s.get("chat_history") or [])
    pending = None if req.new_chat else s.get("pending_analysis")

    # ── あいまい/不可能チェック ──
    needs_clarify, clarify_text = _needs_clarification(req.message, pending)
    if needs_clarify:
        chat_history.append({"role": "user",      "content": req.message})
        chat_history.append({"role": "assistant",  "content": clarify_text})
        sess.update_session(
            sid,
            chat_history=chat_history,
            pending_analysis={"original_request": req.message},
        )
        return {
            "text": clarify_text,
            "graphs": [],
            "raw": clarify_text,
            "clarification_needed": True,
        }

    # ── pending がある場合は元の依頼と補足を統合 ──
    effective_message = req.message
    if pending:
        effective_message = (
            "前回の分析依頼: " + str(pending.get("original_request", "")) + "\n"
            "今回の補足回答: " + req.message + "\n"
            "上記を統合して、ユーザーが本来見たい分析を実行してください。"
        )
        sess.update_session(sid, pending_analysis=None)

    # ── LLM 呼び出し ──
    patched_msg, extra_system = build_fuzzy_context(df, effective_message)
    chat_history.append({"role": "user", "content": patched_msg})

    raw_response = await run_in_threadpool(call_llm_chat, summary_text, chat_history, extra_system)
    chat_history.append({"role": "assistant", "content": raw_response})
    sess.update_session(sid, chat_history=chat_history, pending_analysis=None)

    # ── レスポンスパース & グラフ生成 ──
    text_part, code_blocks = parse_llm_response(raw_response)

    graphs = []
    extra_texts: list[str] = []
    for code in code_blocks:
        result = await run_in_threadpool(exec_graph_code, code, df)
        graphs.append(result)
        if result.get("text_output"):
            extra_texts.append(result["text_output"])

    combined_text = text_part
    if extra_texts:
        combined_text = (text_part + "\n\n" + "\n\n".join(extra_texts)).strip()

    # チャット結果をセッションに蓄積（Excel エクスポート用）
    chat_analyses = list(s.get("chat_analyses") or [])
    chat_analyses.append({
        "question":         req.message,
        "effective_message": effective_message,
        "new_chat":         bool(req.new_chat),
        "text":             combined_text,
        "graphs":           [g for g in graphs if g.get("image_b64")],
    })
    sess.update_session(sid, chat_analyses=chat_analyses)

    return {
        "text":                 combined_text,
        "graphs":               graphs,
        "raw":                  raw_response,
        "clarification_needed": False,
    }


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
    return {"ok": True}
