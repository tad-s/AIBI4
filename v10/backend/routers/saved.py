"""保存済み分析（ダッシュボード）の CRUD。"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core import saved
from semantic.query import QuerySpec

router = APIRouter(prefix="/api")


class SaveReq(BaseModel):
    name: str
    spec: QuerySpec
    dataset: str = "izakaya"


@router.get("/saved")
def list_saved(dataset: str | None = None):
    return {"items": saved.list_saved(dataset)}


@router.post("/saved")
def create_saved(req: SaveReq):
    return saved.add_saved(req.name, req.spec.model_dump(), req.dataset)


@router.delete("/saved/{view_id}")
def remove_saved(view_id: str):
    if not saved.delete_saved(view_id):
        raise HTTPException(status_code=404, detail="保存済み分析が見つかりません。")
    return {"ok": True}
