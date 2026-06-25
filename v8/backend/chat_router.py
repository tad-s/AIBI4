"""
chat_router.py — チャット・音声入力エンドポイント
POST /api/chat/{sid}         LLM チャット（テキスト → テキスト + グラフ）
POST /api/voice/{sid}        音声 → テキスト（Whisper）
DELETE /api/chat/{sid}       チャット履歴クリア
"""
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


@router.post("/chat/{sid}")
async def chat(sid: str, req: ChatRequest):
    s = sess.get_session(sid)
    if not s:
        raise HTTPException(status_code=404, detail="セッションが見つかりません。")
    df = s.get("df")
    if df is None:
        raise HTTPException(status_code=400, detail="データが取得されていません。")
    summary_text = s.get("summary_text", "")
    chat_history: list[dict] = s.get("chat_history", [])

    # ファジー補正
    patched_msg, extra_system = build_fuzzy_context(df, req.message)

    # チャット履歴にユーザーメッセージ追加
    chat_history.append({"role": "user", "content": patched_msg})

    # LLM 呼び出し
    raw_response = await run_in_threadpool(
        call_llm_chat, summary_text, chat_history, extra_system
    )

    # チャット履歴にアシスタント返答追加
    chat_history.append({"role": "assistant", "content": raw_response})
    sess.update_session(sid, chat_history=chat_history)

    # レスポンスのパース
    text_part, code_blocks = parse_llm_response(raw_response)

    # コード実行（グラフ生成）
    graphs = []
    extra_texts: list[str] = []
    for code in code_blocks:
        result = await run_in_threadpool(exec_graph_code, code, df)
        graphs.append(result)
        if result.get("text_output"):
            extra_texts.append(result["text_output"])

    # コード内の print() 出力をテキストに追記
    combined_text = text_part
    if extra_texts:
        combined_text = (text_part + "\n\n" + "\n\n".join(extra_texts)).strip()

    # チャット結果をセッションに蓄積（Excel エクスポート用）
    chat_analyses = list(s.get("chat_analyses") or [])
    chat_analyses.append({
        "question": req.message,
        "text":     combined_text,
        "graphs":   [g for g in graphs if g.get("image_b64")],
    })
    sess.update_session(sid, chat_analyses=chat_analyses)

    return {
        "text": combined_text,
        "graphs": graphs,
        "raw": raw_response,
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
    sess.update_session(sid, chat_history=[], chat_analyses=[])
    return {"ok": True}
