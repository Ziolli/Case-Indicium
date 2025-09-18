# src/case_indicium/agent/schemas.py
from __future__ import annotations

"""
Typed data models used across the SRAG agent.

These Pydantic schemas define the contract between:
- the ELT/gold layer and the web app,
- the agent tools (NL→SQL, reporting, news fetching) and the UI,
- and the report generation pipeline.

Compatibility note:
  Field names and shapes were kept the same as the original PT-BR version
  so callers do not need to change. Only docstrings/descriptions were added
  and types annotated more explicitly where helpful.
"""

from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field


class KPIs30d(BaseModel):
    """
    KPI snapshot for the last 30 days (plus a 7-day momentum view).

    Attributes:
        cases_7d: Cases counted in the last 7 days.
        cases_prev_7d: Cases counted in the 7 days immediately before that.
        growth_7d_pct: Percent change between the two 7-day windows.
        cfr_closed_30d_pct: Case Fatality Ratio among closed cases in 30 days (percent).
        icu_rate_30d_pct: Share of cases with ICU passage in 30 days (percent).
        vaccinated_rate_30d_pct: Share of notified cases with vaccination recorded (percent).
    """

    cases_7d: int = Field(..., description="Cases in the most recent 7-day window.")
    cases_prev_7d: int = Field(..., description="Cases in the previous 7-day window.")
    growth_7d_pct: Optional[float] = Field(
        None, description="Percent growth (current 7d vs previous 7d)."
    )

    cfr_closed_30d_pct: Optional[float] = Field(
        None, description="CFR among closed cases in the last 30 days (percent)."
    )
    icu_rate_30d_pct: Optional[float] = Field(
        None, description="ICU passage rate in the last 30 days (percent)."
    )
    vaccinated_rate_30d_pct: Optional[float] = Field(
        None, description="Share of cases with vaccination recorded (percent)."
    )


class SeriesPoint(BaseModel):
    """
    A single point in a time series.

    Attributes:
        x: Calendar date of the observation.
        y: Numeric value at that date.
    """

    x: date = Field(..., description="Date for this observation.")
    y: float = Field(..., description="Value at date x.")


class Series(BaseModel):
    """
    Labeled time series (daily or monthly).

    Attributes:
        label: Legend/title for the series (e.g., 'Daily cases (30d)').
        points: Ordered list of points. Expected to be sorted by x ascending.
    """

    label: str = Field(..., description="Series label.")
    points: List[SeriesPoint] = Field(
        default_factory=list, description="Ordered points for the series."
    )


class NewsItem(BaseModel):
    """
    Minimal news item used by the agent's news feed.

    Attributes:
        title: Headline/title of the article.
        url: Canonical article URL.
        source: Publisher/source name.
        published_at: ISO-8601 timestamp string.
        summary: Optional short summary/abstract.
    """

    title: str = Field(..., description="Article title/headline.")
    url: str = Field(..., description="Canonical URL for the article.")
    source: str = Field(..., description="Publisher/source name.")
    published_at: str = Field(..., description="ISO-8601 datetime string.")
    summary: Optional[str] = Field(None, description="Optional short abstract.")


class ReportInput(BaseModel):
    """
    Input envelope for generating the standard report.

    Attributes:
        scope: 'br' for Brazil-wide or 'uf' for a specific state.
        uf: Optional UF code when scope == 'uf' (e.g., 'SP', 'MG').
    """

    scope: str = Field(
        ...,
        pattern=r"^(br|uf)$",
        description="Report scope: 'br' (Brazil) or 'uf' (specific state).",
    )
    uf: Optional[str] = Field(
        None,
        description="UF code (e.g., 'SP', 'MG') when scope='uf'.",
    )


class ReportOutput(BaseModel):
    """
    Output payload returned by the report generator.

    Attributes:
        kpis: KPI snapshot for the last 30 days.
        daily_series_30d: Daily series (last 30 days) for display.
        monthly_series_12m: Monthly series (last 12 months) for display.
        news: Curated list of recent news items (already filtered/ranked).
        report_md: Markdown-rendered full report.
        assets: List of asset paths/URLs (e.g., images) optionally produced.
        as_of_day: Optional date string (YYYY-MM-DD) for data currency.
    """

    kpis: KPIs30d
    daily_series_30d: Series
    monthly_series_12m: Series
    news: List[NewsItem]
    report_md: str
    assets: List[str]
    as_of_day: Optional[str] = Field(
        None, description="Reference date (YYYY-MM-DD) the report is based on."
    )
