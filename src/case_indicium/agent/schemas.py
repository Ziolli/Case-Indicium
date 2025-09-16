from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date

class KPIs30d(BaseModel):
    cases_7d: int
    cases_prev_7d: int
    growth_7d_pct: Optional[float]

    cfr_closed_30d_pct: Optional[float]
    icu_rate_30d_pct: Optional[float]
    vaccinated_rate_30d_pct: Optional[float]

class SeriesPoint(BaseModel):
    x: date
    y: float

class Series(BaseModel):
    label: str
    points: List[SeriesPoint]

class NewsItem(BaseModel):
    title: str
    url: str
    source: str
    published_at: str  # ISO string
    summary: Optional[str] = None

class ReportInput(BaseModel):
    scope: str = Field(..., pattern="^(br|uf)$")
    uf: Optional[str] = None

class ReportOutput(BaseModel):
    kpis: KPIs30d
    daily_series_30d: Series
    monthly_series_12m: Series
    news: List[NewsItem]
    report_md: str
    assets: List[str]
