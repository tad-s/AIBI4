"""QuerySpec — 分析リクエストの構造化表現。

LLM も UI もこの形で分析を指定する。生SQL・生コードは介在しない。
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

ChartType = Literal["kpi", "bar", "line", "area", "pie", "table"]


class Filters(BaseModel):
    months: list[str] = Field(default_factory=list)
    stores: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    customer_layers: list[str] = Field(default_factory=list)
    weather: list[str] = Field(default_factory=list)
    hour_min: Optional[int] = None
    hour_max: Optional[int] = None
    dow: list[int] = Field(default_factory=list)


class QuerySpec(BaseModel):
    metric: str
    dimensions: list[str] = Field(default_factory=list)   # 0〜2軸
    filters: Filters = Field(default_factory=Filters)
    chart_type: ChartType = "bar"
    sort: Literal["value_desc", "value_asc", "dim_asc"] = "value_desc"
    limit: int = 20
    title: Optional[str] = None
