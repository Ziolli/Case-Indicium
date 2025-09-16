from __future__ import annotations
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pathlib import Path
from .sql_client import SQLClient
from .metrics import get_kpis_30d_br, get_daily_30d_br, get_monthly_12m_br, get_as_of_day
from .news_client import fetch_recent_news_srag
from .charting import plot_series
from .schemas import ReportInput, ReportOutput
from .prompt import SYSTEM_PROMPT_PT, build_user_prompt
from .llm_router import generate_text

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"

def render_report_md(ctx: dict) -> str:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(disabled_extensions=("md",))
    )
    tpl = env.get_template("report.md.j2")
    return tpl.render(**ctx)

def _series_to_points(series) -> list[dict]:
    pts = []
    for p in series.points:
        x = p.x.isoformat() if hasattr(p.x, "isoformat") else str(p.x)
        pts.append({"x": x, "y": float(p.y)})
    return pts

def build_report(inp: ReportInput) -> ReportOutput:
    sql = SQLClient()

    as_of_day = get_as_of_day(sql)
    kpis = get_kpis_30d_br(sql)
    daily = get_daily_30d_br(sql)
    monthly = get_monthly_12m_br(sql)

    # Charts em disco
    daily_png = plot_series(daily, "daily_30d.png")
    monthly_png = plot_series(monthly, "monthly_12m.png")

    # News (PlaceHolder/Cache)
    news = fetch_recent_news_srag(limit=5)

    # User Prompt Structured
    user_prompt = build_user_prompt(
        scope="br",
        uf=None,
        as_of_day=as_of_day,
        kpis=kpis.dict(),
        daily_series_30d=_series_to_points(daily),
        monthly_series_12m=_series_to_points(monthly),
        news=[n.dict() for n in news],
        notes=[
            "ICU rate is % of cases with ICU admission (not bed occupancy).",
            "Vaccinated rate is % among notified cases (not population coverage).",
        ],
    )

    # Text to Report (FallBack OpenAI -> Groq)
    body_md = generate_text(user_prompt, SYSTEM_PROMPT_PT, temperature=0.2, max_tokens=1200)

    # Final Render (imgs)
    md = render_report_md({
        "body_md": body_md,
        "daily_png": daily_png,
        "monthly_png": monthly_png,
    })

    return ReportOutput(
        kpis=kpis,
        daily_series_30d=daily,
        monthly_series_12m=monthly,
        news=news,
        report_md=md,
        assets=[daily_png, monthly_png],
    )
