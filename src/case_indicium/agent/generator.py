# src/case_indicium/agent/generator.py
"""
Report generation orchestration for the SRAG agent.

This module pulls KPIs and time series from DuckDB, fetches recent SRAG news,
assembles a structured prompt, calls the LLM to produce a narrative, and
renders a final Markdown report via Jinja2.

Design goals:
- Clear separation of concerns (data fetch, prompt build, LLM call, rendering)
- Dependency injection for SQL client, news provider and LLM generator (easy to test)
- Defensive typing and logging for observability
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Callable, List, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .sql_client import SQLClient
from .metrics import get_as_of_day, get_daily_30d_br, get_kpis_30d_br, get_monthly_12m_br
from .news_client import fetch_recent_news_srag
from .prompt import SYSTEM_PROMPT_PT, build_user_prompt
from .schemas import ReportInput, ReportOutput

# ------------------------------------------------------------------------------
# Constants & logger
# ------------------------------------------------------------------------------
TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
DEFAULT_NEWS_LIMIT = 5

log = logging.getLogger(__name__)


# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------
def _series_to_points(series) -> list[dict]:
    """
    Convert a Series(pydantic) into a list of {'x': iso-date, 'y': float} dicts.
    NaN and non-numeric 'y' are filtered out.
    """
    out: list[dict] = []
    for p in getattr(series, "points", []) or []:
        x = p.x.isoformat() if hasattr(p.x, "isoformat") else str(p.x)
        try:
            y = float(p.y)
        except Exception:
            continue
        # filter NaN (self-inequality check)
        if y == y:
            out.append({"x": x, "y": y})
    return out


def _render_report_md(
    body_md: str,
    *,
    daily_png: Optional[str] = None,
    monthly_png: Optional[str] = None,
) -> str:
    """
    Render the final Markdown report using the Jinja2 template.

    Parameters
    ----------
    body_md : str
        The narrative body (already produced by the LLM).
    daily_png : Optional[str]
        Optional path/URL to a daily chart image to embed.
    monthly_png : Optional[str]
        Optional path/URL to a monthly chart image to embed.

    Returns
    -------
    str
        Final Markdown content.
    """
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(disabled_extensions=("md",)),
    )
    tpl = env.get_template("report.md.j2")
    return tpl.render(body_md=body_md, daily_png=daily_png, monthly_png=monthly_png)


# ------------------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------------------
def build_report(
    inp: ReportInput,
    *,
    sql: Optional[SQLClient] = None,
    news_fetcher: Callable[[int], List] = fetch_recent_news_srag,
    llm_generate: Optional[Callable[[str, str], str]] = None,
) -> ReportOutput:
    """
    Build the SRAG report (currently BR-scope). Uses dependency injection to
    allow alternative SQL clients, news providers, and LLM backends in tests.

    Parameters
    ----------
    inp : ReportInput
        Report scope payload. At the moment, only 'br' is supported in this function.
    sql : Optional[SQLClient]
        Custom SQLClient (for tests/mocks). Defaults to a new SQLClient().
    news_fetcher : Callable[[int], List]
        Function that fetches news items, signature: (limit) -> List[NewsItem].
    llm_generate : Optional[Callable[[str, str], str]]
        Function that accepts (user_prompt, system_prompt) and returns a Markdown string.

    Returns
    -------
    ReportOutput
        Structured report with KPIs, series, news, markdown and assets list.

    Notes
    -----
    - If `inp.scope == "uf"`, this function will still fetch BR aggregates and log a warning.
      A dedicated UF-aware variant can be implemented if needed.
    """
    t0 = time.perf_counter()
    sql = sql or SQLClient()

    if inp.scope != "br":
        log.warning("build_report currently supports BR scope only. Received scope=%s", inp.scope)

    # --- Fetch data (DuckDB) ---------------------------------------------------
    t_db = time.perf_counter()
    as_of_day = get_as_of_day(sql)
    kpis = get_kpis_30d_br(sql)
    daily = get_daily_30d_br(sql)
    monthly = get_monthly_12m_br(sql)
    db_ms = int((time.perf_counter() - t_db) * 1000)

    daily_points = _series_to_points(daily)
    monthly_points = _series_to_points(monthly)

    # --- Fetch news (cached/provider) -----------------------------------------
    t_news = time.perf_counter()
    try:
        news = news_fetcher(limit=DEFAULT_NEWS_LIMIT)
    except Exception as e:
        log.warning("news_fetcher failed: %s", e)
        news = []
    news_ms = int((time.perf_counter() - t_news) * 1000)

    # --- Build LLM prompt (PT-BR system prompt remains intentional) ------------
    # The notes below clarify the interpretation of certain indicators.
    notes = [
        "ICU rate represents the % of cases with an ICU stay (it is NOT bed occupancy).",
        "Vaccinated rate is the % among notified cases (it is NOT population coverage).",
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

    # --- LLM text generation ---------------------------------------------------
    # Lazy import to avoid circular deps on module load.
    from .llm_router import generate_text  # noqa: WPS433 (intentional late import)

    if llm_generate is None:
        llm_generate = lambda u, s: generate_text(u, s, temperature=0.2, max_tokens=1200)  # noqa: E731

    t_llm = time.perf_counter()
    try:
        body_md = llm_generate(user_prompt, SYSTEM_PROMPT_PT)
    except Exception as e:
        log.exception("LLM generation failed: %s", e)
        body_md = (
            "## Report generation unavailable\n\n"
            "An error occurred while generating the narrative. "
            "The KPIs and time series below remain valid.\n"
        )
    llm_ms = int((time.perf_counter() - t_llm) * 1000)

    # --- Render final Markdown -------------------------------------------------
    final_md = _render_report_md(body_md, daily_png=None, monthly_png=None)

    # --- Log timing ------------------------------------------------------------
    total_ms = int((time.perf_counter() - t0) * 1000)
    log.info(
        "report_generated_ms=%d db_ms=%d news_ms=%d llm_ms=%d items_news=%d",
        total_ms,
        db_ms,
        news_ms,
        llm_ms,
        len(news),
    )

    # --- Return structured output ---------------------------------------------
    return ReportOutput(
        kpis=kpis,
        daily_series_30d=daily,
        monthly_series_12m=monthly,
        news=news,
        report_md=final_md,
        assets=[],
        as_of_day=str(as_of_day) if as_of_day is not None else None,
    )
