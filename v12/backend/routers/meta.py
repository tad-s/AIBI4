"""メタ情報エンドポイント（データセット・月・店舗・指標カタログ）。"""
from fastapi import APIRouter, HTTPException

from ingest.supabase_fetch import fetch_available_months, fetch_stores
from semantic.model import dimension_catalog, metric_catalog

router = APIRouter(prefix="/api")


@router.get("/datasets")
def datasets():
    return {"datasets": [
        {"id": "izakaya", "label": "居酒屋（テング酒場/大ホール）"},
        {"id": "cafe",    "label": "カフェ（Café）"},
        {"id": "bakery",  "label": "ベーカリー（Farine）"},
        {"id": "salon",   "label": "美容院・サロン（Lumière）"},
    ]}


@router.get("/catalog")
def catalog():
    return {"metrics": metric_catalog(), "dimensions": dimension_catalog()}


@router.get("/months")
async def months(dataset: str = "izakaya"):
    try:
        return {"months": await fetch_available_months(dataset)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stores")
async def stores(dataset: str = "izakaya"):
    try:
        return {"stores": await fetch_stores(dataset)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
