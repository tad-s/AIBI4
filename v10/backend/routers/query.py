"""クエリ実行・ダッシュボード（プリセット一括実行）。"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.duck import store
from semantic import engine, presets
from semantic.query import Filters, QuerySpec

router = APIRouter(prefix="/api")


class QueryReq(BaseModel):
    spec: QuerySpec
    global_filters: Filters | None = None


class DashboardReq(BaseModel):
    global_filters: Filters | None = None


def merge_filters(spec_f: Filters, glob: Filters | None) -> Filters:
    """spec のフィルタを優先し、空欄はグローバルフィルタで補う。"""
    if glob is None:
        return spec_f
    merged = spec_f.model_copy(deep=True)
    for field in ["months", "stores", "categories", "customer_layers", "weather", "dow"]:
        if not getattr(merged, field):
            setattr(merged, field, getattr(glob, field))
    for field in ["hour_min", "hour_max"]:
        if getattr(merged, field) is None:
            setattr(merged, field, getattr(glob, field))
    return merged


def _run(session, spec: QuerySpec, glob: Filters | None):
    spec = spec.model_copy(deep=True)
    spec.filters = merge_filters(spec.filters, glob)
    return engine.run(session, spec)


@router.post("/sessions/{sid}/query")
def run_query(sid: str, req: QueryReq):
    session = store.get(sid)
    if session is None:
        raise HTTPException(status_code=404, detail="セッションが見つかりません。")
    try:
        return _run(session, req.spec, req.global_filters)
    except engine.SpecError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{sid}/dashboard")
def dashboard(sid: str, req: DashboardReq):
    session = store.get(sid)
    if session is None:
        raise HTTPException(status_code=404, detail="セッションが見つかりません。")

    kpis, tiles = [], []
    for raw in presets.KPI_SPECS:
        try:
            res = _run(session, QuerySpec.model_validate(raw), req.global_filters)
            # 月次スパークライン＋前期比デルタを付与
            try:
                monthly = _run(
                    session,
                    QuerySpec.model_validate({**raw, "dimensions": ["month"],
                                              "chart_type": "line", "sort": "dim_asc", "limit": 36}),
                    req.global_filters,
                )
                vals = [r["value"] for r in monthly["rows"] if r["value"] is not None]
                res["spark"] = vals
                if len(vals) >= 2 and vals[-2]:
                    res["delta"] = (vals[-1] - vals[-2]) / abs(vals[-2])
            except Exception:
                pass
            kpis.append(res)
        except Exception:
            pass
    for raw in presets.TILE_SPECS:
        try:
            tiles.append(_run(session, QuerySpec.model_validate(raw), req.global_filters))
        except Exception:
            pass
    return {"kpis": kpis, "tiles": tiles}
