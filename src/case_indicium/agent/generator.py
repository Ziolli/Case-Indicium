# src/case_indicium/agent/generator.py
"""Builds a text-first SRAG report using DuckDB KPIs/series + LLM synthesis.

The UI (Streamlit) is responsible for plotting charts; this module just returns data + markdown.
"""

from __future__ import annotations
from pathlib import Path
from typing import Dict, Any, Optional, List

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .sql_client import SQLClient
from .metrics import (
    get_kpis_30d_br,
    get_daily_30d_br,
    get_monthly_12m_br,
    get_as_of_day,
)
from .news_client import fetch_recent_news_srag
from .schemas import ReportInput, ReportOutput
from .prompt import SYSTEM_PROMPT_PT, build_user_prompt
from .llm_router import generate_text


TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"


def _series_to_points(series) -> list[dict]:
    """Convert Series(label, points) -> [{'x': iso, 'y': float}, ...]."""
    out: list[dict] = []
    for p in series.points:
        x = p.x.isoformat() if hasattr(p.x, "isoformat") else str(p.x)
        out.append({"x": x, "y": float(p.y)})
    return out


def render_report_md(body_md: str, daily_png: Optional[str] = None, monthly_png: Optional[str] = None) -> str:
    """Render final markdown via Jinja template. Charts are optional (currently unused)."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(disabled_extensions=("md",)),
    )
    tpl = env.get_template("report.md.j2")
    return tpl.render(body_md=body_md, daily_png=daily_png, monthly_png=monthly_png)


def build_report(inp: ReportInput) -> ReportOutput:
    """Build the BR-scoped report (PoC)."""
    sql = SQLClient()

    # Scope BR (extend later for UF with queries_*_UF)
    as_of_day = get_as_of_day(sql)
    kpis = get_kpis_30d_br(sql)
    daily = get_daily_30d_br(sql)
    monthly = get_monthly_12m_br(sql)

    # Series -> payload-friendly
    daily_points = _series_to_points(daily)
    monthly_points = _series_to_points(monthly)

    # Notícias (placeholder/cache)
    news = fetch_recent_news_srag(limit=5)

    # Prompt estruturado (PT-BR) para LLM
    notes = [
        "A taxa de UTI é % de casos com passagem por UTI (não é ocupação de leitos).",
        "A taxa de 'vacinados' é % entre casos notificados (não é cobertura da população).",
    ]
    user_prompt = build_user_prompt(
        scope="br",
        uf=None,
        as_of_day=as_of_day,
        kpis=kpis.dict(),
        daily_series_30d=daily_points,
        monthly_series_12m=monthly_points,
        news=[n.dict() for n in news],
        notes=notes,
    )

    body_md = generate_text(user_prompt, SYSTEM_PROMPT_PT, temperature=0.2, max_tokens=1200)

    # Render final (sem imagens; a UI faz os gráficos)
    md = render_report_md(body_md, daily_png=None, monthly_png=None)

    return ReportOutput(
        kpis=kpis,
        daily_series_30d=daily,
        monthly_series_12m=monthly,
        news=news,
        report_md=md,
        assets=[],  # no images saved here
    )
