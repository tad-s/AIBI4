"""QuerySpec → DuckDB SQL → 結果。

決定論的な集計エンジン。LLM が生成した仕様も UI が組んだ仕様も、
すべてここを通して実行されるため、集計ロジックは1箇所でテスト・監査できる。
"""
from __future__ import annotations

import pandas as pd

from core.duck import Session
from semantic.model import DIMENSIONS, METRICS, Dimension, Metric
from semantic.query import Filters, QuerySpec


class SpecError(ValueError):
    """仕様が現在のデータ構造で実行できない場合。"""


def _q(val: str) -> str:
    """SQL 文字列リテラルのエスケープ。"""
    return "'" + str(val).replace("'", "''") + "'"


def _in_clause(col: str, values: list) -> str:
    if not values:
        return ""
    quoted = ", ".join(_q(v) for v in values)
    return f"{col} IN ({quoted})"


def _build_where(filters: Filters, view: str) -> str:
    conds: list[str] = []
    if filters.months:
        conds.append(_in_clause("year_month", filters.months))
    if filters.stores:
        conds.append(_in_clause("store_name", filters.stores))
    if filters.customer_layers:
        conds.append(_in_clause("customer_layer", filters.customer_layers))
    if filters.weather:
        conds.append(_in_clause("weather_label", filters.weather))
    if filters.dow:
        conds.append("dow IN (" + ", ".join(str(int(d)) for d in filters.dow) + ")")
    if filters.hour_min is not None:
        conds.append(f"hour >= {int(filters.hour_min)}")
    if filters.hour_max is not None:
        conds.append(f"hour <= {int(filters.hour_max)}")

    # カテゴリ/商品フィルタは items 列。orders base の場合は visit_key サブクエリで絞る。
    for col, vals in [("category", filters.categories)]:
        if not vals:
            continue
        if view == "items":
            conds.append(_in_clause(col, vals))
        else:
            sub = _in_clause(col, vals)
            conds.append(f"visit_key IN (SELECT visit_key FROM items WHERE {sub})")

    return (" WHERE " + " AND ".join(c for c in conds if c)) if conds else ""


def _validate(spec: QuerySpec) -> tuple[Metric, list[Dimension]]:
    metric = METRICS.get(spec.metric)
    if metric is None:
        raise SpecError(f"未知の指標です: {spec.metric}")
    dims = []
    for d_id in spec.dimensions[:2]:
        dim = DIMENSIONS.get(d_id)
        if dim is None:
            raise SpecError(f"未知の軸です: {d_id}")
        if metric.view not in dim.views:
            raise SpecError(
                f"「{metric.label}」は伝票単位の指標のため、"
                f"「{dim.label}」（商品単位の軸）では集計できません。"
                f"売上・販売点数など商品単位の指標に変えるか、別の軸を選んでください。"
            )
        dims.append(dim)
    return metric, dims


def build_sql(spec: QuerySpec) -> str:
    metric, dims = _validate(spec)
    view = metric.view

    select_parts = [f"{d.sql} AS dim{i}" for i, d in enumerate(dims)]
    select_parts.append(f"{metric.sql} AS value")

    where = _build_where(spec.filters, view)
    group = ""
    order = ""
    limit = ""
    if dims:
        group = " GROUP BY " + ", ".join(f"{d.sql}" for d in dims)
        if spec.sort == "value_desc":
            order = " ORDER BY value DESC"
        elif spec.sort == "value_asc":
            order = " ORDER BY value ASC"
        else:
            order = " ORDER BY dim0 ASC"
        if spec.limit and spec.limit > 0:
            limit = f" LIMIT {int(spec.limit)}"

    return f"SELECT {', '.join(select_parts)} FROM {view}{where}{group}{order}{limit}"


def run(session: Session, spec: QuerySpec) -> dict:
    """仕様を実行し、フロント描画用の結果 dict を返す。"""
    metric, dims = _validate(spec)
    sql = build_sql(spec)
    df = session.query(sql)

    # 軸ラベルの適用（曜日など）＋ 時間帯の "18時" 表記
    rows = []
    for _, r in df.iterrows():
        v = r["value"]
        row = {"value": None if pd.isna(v) else float(v)}
        for i, d in enumerate(dims):
            raw = r[f"dim{i}"]
            is_na = raw is None or (not isinstance(raw, (list, dict)) and pd.isna(raw))
            row[f"dim{i}"] = _dim_label(d, None if is_na else raw)
            row[f"dim{i}_raw"] = None if is_na else _json_safe(raw)
        rows.append(row)

    return {
        "spec": spec.model_dump(),
        "metric": {"id": metric.id, "label": metric.label, "unit": metric.unit, "fmt": metric.fmt},
        "dimensions": [{"id": d.id, "label": d.label, "kind": d.kind} for d in dims],
        "rows": rows,
        "sql": sql,
        "title": spec.title or _auto_title(metric, dims),
    }


def _json_safe(v):
    try:
        import numpy as np
        if isinstance(v, (np.integer,)):
            return int(v)
        if isinstance(v, (np.floating,)):
            return float(v)
    except Exception:
        pass
    return v


def _dim_label(d: Dimension, raw) -> str:
    if raw is None:
        return "（不明）"
    if d.labels:
        try:
            return d.labels.get(int(raw), str(raw))
        except (ValueError, TypeError):
            return str(raw)
    if d.id == "hour":
        try:
            return f"{int(raw)}時"
        except (ValueError, TypeError):
            return str(raw)
    return str(raw)


def _auto_title(metric: Metric, dims: list[Dimension]) -> str:
    if not dims:
        return metric.label
    return f"{'×'.join(d.label for d in dims)}別 {metric.label}"
