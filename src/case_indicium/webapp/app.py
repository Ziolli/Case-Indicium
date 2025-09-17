"""
Streamlit web app for SRAG reporting (Gold/Silver dashboard + Agent chat).

- KPIs cards (last 30 days)
- Daily (30d) and Monthly (12m) charts with Plotly
- Top-UF bar
- Agent chat (OpenAI→Groq routing; uses your prompt scaffolding)

Run:
  poetry run streamlit run src/case_indicium/webapp/app.py
"""

from __future__ import annotations
import pandas as pd
import base64
import os
from pathlib import Path
from typing import Dict, Any, List, Optional
import streamlit as st
import plotly.express as px
from dotenv import load_dotenv

from case_indicium.agent.intent_router import classify
from case_indicium.agent.tools import run_sql_whitelisted, get_kpis as tool_get_kpis, get_series as tool_get_series, glossary_lookup
from case_indicium.agent.prompt import SYSTEM_PROMPT_PT, build_user_prompt
from case_indicium.agent.llm_router import generate_text
from case_indicium.agent.intent_router import extract_explain_term
from case_indicium.agent.sql_client import SQLClient
from case_indicium.agent.metrics import (
    get_kpis_30d_br,
    get_daily_30d_br,
    get_monthly_12m_br,
    get_as_of_day,
)
from case_indicium.agent.queries import (
    SQL_TOP_UF_CASES_30D,
    SQL_DAILY_30D_UF,
    SQL_MONTHLY_12M_UF,
    SQL_KPIS_30D_UF,
)
from case_indicium.agent.prompt import SYSTEM_PROMPT_PT, build_user_prompt
from case_indicium.agent.llm_router import generate_text


# -------------------------
# Bootstrap
# -------------------------
load_dotenv()  # load .env from project root if present

st.set_page_config(
    page_title="SRAG Dashboard & Agent",
    page_icon="🩺",
    layout="wide",
    menu_items={"Get Help": None, "Report a bug": None, "About": "SRAG PoC – Indicium"},
)

# Small CSS for nicer spacing/cards
st.markdown(
    """
    <style>
    .kpi-card {
        padding: 16px;
        border-radius: 16px;
        background: #0F172A;
        color: #E2E8F0;
        border: 1px solid #1E293B;
    }
    .kpi-value {
        font-size: 1.8rem;
        font-weight: 700;
        margin-top: 4px;
    }
    .kpi-label {
        font-size: 0.95rem;
        color: #94A3B8;
    }
    .section-title {
        margin-top: 0.5rem;
        margin-bottom: 0.5rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# -------------------------
# Helpers
# -------------------------


def style_fig(fig, *, title: str | None = None):
    """Apply a clean dark theme and better hover to a Plotly figure."""
    if title:
        fig.update_layout(title=title)
    fig.update_layout(
        template="plotly_dark",
        height=360,
        margin=dict(l=16, r=16, t=48, b=16),
        hovermode="x unified",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(size=14),
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.08)")
    return fig


def _series_to_df(series) -> pd.DataFrame:
    """Turn Series(label, points[x,y]) into a tidy DataFrame."""
    rows = []
    for p in series.points:
        x = p.x.isoformat() if hasattr(p.x, "isoformat") else str(p.x)
        rows.append({"x": x, "y": float(p.y)})
    return pd.DataFrame(rows)


@st.cache_data(ttl=300)  # cache 5 min
def load_br_data() -> Dict[str, Any]:
    """Load Brazil-scope KPIs and series from DuckDB (read-only)."""
    sql = SQLClient()
    as_of = get_as_of_day(sql)
    kpis = get_kpis_30d_br(sql)
    daily = get_daily_30d_br(sql)
    monthly = get_monthly_12m_br(sql)
    top_ufs = sql.df(SQL_TOP_UF_CASES_30D)

    return {
        "as_of": as_of,
        "kpis": kpis,
        "daily_df": _series_to_df(daily),
        "monthly_df": _series_to_df(monthly),
        "top_ufs": top_ufs,
    }


@st.cache_data(ttl=300)
def load_uf_data(uf: str) -> Dict[str, Any]:
    """Load UF-scope KPIs and series using parameterized queries."""
    sql = SQLClient()
    as_of = get_as_of_day(sql)

    # KPIs
    kpi_df = sql.df(SQL_KPIS_30D_UF, params={"uf": uf})
    if kpi_df.empty:
        kpi_payload = None
    else:
        row = kpi_df.iloc[0]
        kpi_payload = {
            "cases_7d": None,  # optional for UF (i should improve it later.)
            "cases_prev_7d": None,
            "growth_7d_pct": None,
            "cfr_closed_30d_pct": row.get("cfr_closed_30d_pct"),
            "icu_rate_30d_pct": row.get("icu_rate_30d_pct"),
            "vaccinated_rate_30d_pct": row.get("vaccinated_rate_30d_pct"),
        }

    # Series
    daily_df = SQLClient().df(SQL_DAILY_30D_UF, params={"uf": uf})
    monthly_df = SQLClient().df(SQL_MONTHLY_12M_UF, params={"uf": uf})

    return {
        "as_of": as_of,
        "kpis": kpi_payload,
        "daily_df": daily_df.rename(columns={"day": "x", "cases": "y"}),
        "monthly_df": monthly_df.rename(columns={"month": "x", "cases": "y"}),
    }


def kpi_card(label: str, value: Optional[float | int], suffix: str = "", fmt: str = "auto"):
    """Render a KPI card with consistent style."""
    if value is None:
        display = "—"
    else:
        if fmt == "pct":
            display = f"{value:.1f}%"
        elif fmt == "int":
            display = f"{int(value):,}".replace(",", ".")
        else:
            display = str(value)

    st.markdown(
        f"""
        <div class="kpi-card">
          <div class="kpi-label">{label}</div>
          <div class="kpi-value">{display}{suffix}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def plot_line(df: pd.DataFrame, title: str, x_label: str, y_label: str):
    if df.empty:
        st.info("No data to plot.")
        return
    fig = px.line(df, x="x", y="y", markers=True)
    fig.update_traces(hovertemplate=f"<b>%{{x}}</b><br>{y_label}: %{{y:,.0f}}")
    style_fig(fig, title=title)
    st.plotly_chart(fig, use_container_width=True)

def plot_bar(df: pd.DataFrame, title: str, x_label: str, y_label: str):
    if df.empty:
        st.info("No data to plot.")
        return
    fig = px.bar(df, x="x", y="y")
    fig.update_traces(hovertemplate=f"<b>%{{x}}</b><br>{y_label}: %{{y:,.0f}}")
    style_fig(fig, title=title)
    st.plotly_chart(fig, use_container_width=True)

def top_uf_bar(df: pd.DataFrame, title: str):
    if df.empty:
        st.info("No UF data.")
        return
    # Order Desc
    df2 = df.sort_values("cases_30d", ascending=False)
    fig = px.bar(df2, x="uf", y="cases_30d")
    fig.update_traces(hovertemplate="<b>%{x}</b><br>cases (30d): %{y:,.0f}")
    style_fig(fig, title=title)
    st.plotly_chart(fig, use_container_width=True)



def agent_chat(scope: str, uf: Optional[str], as_of_day: Optional[str],
               kpis_dict: Dict[str, Any], daily_df: pd.DataFrame, monthly_df: pd.DataFrame):
    """Conversational agent with tool-usage and simple intent routing (PT-BR)."""
    st.subheader("🤖 Chat do Agente")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_msg = st.chat_input("Pergunte algo (ex.: 'Gerar relatório padrão', 'Explicar CFR', 'Comparar UFs...')")
    if not user_msg:
        return

    st.session_state.messages.append({"role": "user", "content": user_msg})
    with st.chat_message("user"):
        st.markdown(user_msg)

    intent = classify(user_msg)

    # 1) Explicação de termos (sem LLM)
    if intent.kind == "explain":
        term = extract_explain_term(user_msg)       # novo
        desc = glossary_lookup(term)
        reply = f"**{term}** — {desc}"
        st.session_state.messages.append({"role": "assistant", "content": reply})
        with st.chat_message("assistant"):
            st.markdown(reply)
        return

    # 2) Comparações rápidas (sem LLM) — exemplo: Top UFs por casos (30d)
    if intent.kind == "compare":
        df_top = run_sql_whitelisted("SQL_TOP_UF_CASES_30D")
        st.session_state.messages.append({"role": "assistant", "content": "Listando Top UFs por casos (30 dias)."})
        with st.chat_message("assistant"):
            st.markdown("**Top UFs por casos (30 dias):**")
            st.dataframe(df_top)
        return

    # 3) Tendências (mensagem curta; gráficos já estão no painel)
    if intent.kind == "trend":
        reply = (
            f"Mostrando tendências para **{'Brasil' if scope=='br' else f'UF {uf}'}**, "
            f"as_of **{as_of_day or 'n/a'}**. Diário = últimos 30 dias; Mensal = últimos 12 meses."
        )
        st.session_state.messages.append({"role": "assistant", "content": reply})
        with st.chat_message("assistant"):
            st.markdown(reply)
        return

    # 4) Relatório padrão (ou fallback para síntese via LLM)
    daily_points = [{"x": r["x"], "y": r["y"]} for _, r in daily_df.iterrows()]
    monthly_points = [{"x": r["x"], "y": r["y"]} for _, r in monthly_df.iterrows()]
    notes = [
        "A taxa de UTI é % de casos com passagem por UTI (não é ocupação de leitos).",
        "A taxa de 'vacinados' é % entre casos notificados (não é cobertura da população).",
    ]
    user_payload = build_user_prompt(
        scope=scope, uf=uf, as_of_day=as_of_day,
        kpis=kpis_dict or {}, daily_series_30d=daily_points,
        monthly_series_12m=monthly_points, news=[], notes=notes,
    )
    try:
        text = generate_text(user_payload, SYSTEM_PROMPT_PT, temperature=0.2, max_tokens=1100)
    except Exception as e:
        text = f"Erro ao chamar o LLM: {e}"

    st.session_state.messages.append({"role": "assistant", "content": text})
    with st.chat_message("assistant"):
        st.markdown(text)

# -------------------------
# UI
# -------------------------
# --- Header with fixed top-left logo + title ---
PROJECT_ROOT = Path(__file__).resolve().parents[3]
LOGO= PROJECT_ROOT / "assets" / "indicium_logo.png"
st.title("SRAG — Dashboard & Agent")
st.caption("Technical Case • Analytics + LLM Routed (OpenAI → Groq)")

# Sidebar: logo no topo + filtros
with st.sidebar:
    if LOGO.exists():
        st.image(str(LOGO), use_container_width=True)
    else:
        st.markdown("**Indicium**")

    st.header("Filters")
    scope = st.radio("Scope", ["Brazil", "UF"], horizontal=True)
    chosen_uf = None
    if scope == "UF":
        br = load_br_data()
        uf_opts = sorted(br["top_ufs"]["uf"].unique().tolist())
        chosen_uf = st.selectbox(
            "Select UF",
            uf_opts,
            index=(uf_opts.index("SP") if "SP" in uf_opts else 0),
        )
# Load data
if scope == "Brazil":
    data = load_br_data()
    as_of = data["as_of"]
    kpis = data["kpis"]
    daily_df = data["daily_df"]
    monthly_df = data["monthly_df"]
    top_ufs = data["top_ufs"]
else:
    data = load_uf_data(chosen_uf)
    as_of = data["as_of"]
    kpis = data["kpis"]
    daily_df = data["daily_df"]
    monthly_df = data["monthly_df"]
    top_ufs = pd.DataFrame()  # not used in UF scope

# Header info
st.caption(f"Data as of: **{as_of or 'n/a'}**")

# KPI row
col1, col2, col3, col4 = st.columns(4)
with col1:
    kpi_card("Cases (last 7d) vs prev 7d", kpis.get("growth_7d_pct") if isinstance(kpis, dict) else kpis.growth_7d_pct, suffix="", fmt="pct")
with col2:
    # CFR % (closed cases, 30d)
    val = kpis.get("cfr_closed_30d_pct") if isinstance(kpis, dict) else kpis.cfr_closed_30d_pct
    kpi_card("CFR (closed, 30d)", val, fmt="pct")
with col3:
    val = kpis.get("icu_rate_30d_pct") if isinstance(kpis, dict) else kpis.icu_rate_30d_pct
    kpi_card("ICU rate (30d)", val, fmt="pct")
with col4:
    val = kpis.get("vaccinated_rate_30d_pct") if isinstance(kpis, dict) else kpis.vaccinated_rate_30d_pct
    kpi_card("Vaccinated rate (30d)", val, fmt="pct")

st.markdown("### Trends", help="Daily = last 30 days; Monthly = last 12 months.")

left, right = st.columns(2)
with left:
    plot_line(daily_df, "Daily cases (last 30 days)", "date", "cases")
with right:
    plot_bar(monthly_df, "Monthly cases (last 12 months)", "month", "cases")

if scope == "Brazil":
    st.markdown("### Top UFs by cases (last 30 days)")
    top_uf_bar(top_ufs, "Top UFs by cases (30d)")

st.divider()
agent_chat("br" if scope == "Brazil" else "uf", chosen_uf if scope == "UF" else None, as_of, kpis.dict() if hasattr(kpis, "dict") else kpis, daily_df, monthly_df)
