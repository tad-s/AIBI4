"""AI Ask — 自然言語 → 仕様 → 実行（継続チャット・確認フロー対応）。"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.duck import store
from llm import spec_generator
from routers.query import _run
from semantic import engine
from semantic.query import Filters, QuerySpec

router = APIRouter(prefix="/api")


class AskReq(BaseModel):
    message: str
    global_filters: Filters | None = None
    history: list[dict] = []


@router.post("/sessions/{sid}/ask")
def ask(sid: str, req: AskReq):
    session = store.get(sid)
    if session is None:
        raise HTTPException(status_code=404, detail="セッションが見つかりません。")

    gen = spec_generator.generate(req.message, session.meta, req.history)
    action = gen.get("action")

    if action != "query" or not gen.get("spec"):
        # clarify / impossible
        return {"action": action, "message": gen.get("message", ""), "result": None}

    try:
        spec = QuerySpec.model_validate(gen["spec"])
        result = _run(session, spec, req.global_filters)
    except engine.SpecError as e:
        # 実行不能だった場合は確認フローに切り替える
        return {"action": "clarify", "message": str(e), "result": None}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"action": "query", "message": gen.get("message", ""), "result": result}
