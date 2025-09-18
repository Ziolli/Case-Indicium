# src/case_indicium/webapp/app.py
"""
Streamlit web app for SRAG: dashboard + agent chat (PT-BR).

Features
--------
- KPI cards (30d window)
- Daily (30d) and Monthly (12m) charts (Plotly)
- Top-UF bar (BR scope)
- Agent chat routed by intent_router.handle()  ← greet/news/report/explain/trend/dataqa/nlquery

Run:
  poetry run streamlit run src/case_indicium/webapp/app.py
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv

from case_indicium.agent.sql_client import SQLClient
from case_indicium.agent.metrics import (
    get_as_of_day,
    get_kpis_30d_br,
    get_daily_30d_br,
    get_monthly_12m_br,
)
from case_indicium.agent.intent_router import handle as agent_handle, Intent
from case_indicium.agent.queries import (
    SQL_TOP_UF_CASES_30D,
    SQL_DAILY_30D_UF,
    SQL_MONTHLY_12M_UF,
    SQL_KPIS_30D_UF,
)

# -----------------------------------------------------------------------------
# Bootstrap
# -----------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[3]
# carrega .env da raiz do projeto (não sobrescreve variáveis já exportadas)
load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=False, encoding="utf-8")

st.set_page_config(
    page_title="SRAG • Dashboard & Agente",
    page_icon="🦠",
    layout="wide",
    menu_items={"Get Help": None, "Report a bug": None, "About": "SRAG PoC — Indicium"},
)

# Minimal CSS polish
st.markdown(
    """
    <style>
      .kpi-card { padding:16px; border-radius:16px; background:#0F172A; color:#E2E8F0; border:1px solid #1E293B; }
      .kpi-value { font-size:1.8rem; font-weight:700; margin-top:4px; }
      .kpi-label { font-size:0.95rem; color:#94A3B8; }
    </style>
    """,
    unsafe_allow_html=True,
)

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def style_fig(fig, *, title: Optional[str] = None):
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
    """Convert Series(label, points[x,y]) into a tidy DataFrame."""
    rows = []
    for p in series.points:
        x = p.x.isoformat() if hasattr(p.x, "isoformat") else str(p.x)
        rows.append({"x": x, "y": float(p.y)})
    return pd.DataFrame(rows)


def kpi_card(label: str, value: Optional[float | int], *, fmt: str = "auto"):
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
          <div class="kpi-value">{display}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def plot_line(df: pd.DataFrame, title: str, y_label: str):
    if df.empty:
        st.info("Sem dados para o gráfico.")
        return
    fig = px.line(df, x="x", y="y", markers=True)
    fig.update_traces(hovertemplate=f"<b>%{{x}}</b><br>{y_label}: %{{y:,.0f}}")
    style_fig(fig, title=title)
    st.plotly_chart(fig, use_container_width=True)


def plot_bar(df: pd.DataFrame, title: str, y_label: str):
    if df.empty:
        st.info("Sem dados para o gráfico.")
        return
    fig = px.bar(df, x="x", y="y")
    fig.update_traces(hovertemplate=f"<b>%{{x}}</b><br>{y_label}: %{{y:,.0f}}")
    style_fig(fig, title=title)
    st.plotly_chart(fig, use_container_width=True)


def top_uf_bar(df: pd.DataFrame, title: str):
    if df.empty:
        st.info("Sem dados de UF.")
        return
    df2 = df.sort_values("cases_30d", ascending=False)
    fig = px.bar(df2, x="uf", y="cases_30d")
    fig.update_traces(hovertemplate="<b>%{x}</b><br>casos (30d): %{y:,.0f}")
    style_fig(fig, title=title)
    st.plotly_chart(fig, use_container_width=True)


# -----------------------------------------------------------------------------
# Data loaders (cached)
# -----------------------------------------------------------------------------

@st.cache_data(ttl=300)
def load_br_data() -> Dict[str, Any]:
    """Load Brazil-scope KPIs and series from DuckDB."""
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
    """Load UF-scope KPIs and series from DuckDB (parameterized)."""
    sql = SQLClient()
    as_of = get_as_of_day(sql)

    kpi_df = sql.df(SQL_KPIS_30D_UF, params={"uf": uf})
    if kpi_df.empty:
        kpi_payload: Dict[str, Any] = {
            "growth_7d_pct": None,
            "cfr_closed_30d_pct": None,
            "icu_rate_30d_pct": None,
            "vaccinated_rate_30d_pct": None,
        }
    else:
        row = kpi_df.iloc[0]
        kpi_payload = {
            "growth_7d_pct": None,  # (opcional) adicionar via SQL_GROWTH_7D_UF no futuro
            "cfr_closed_30d_pct": row.get("cfr_closed_30d_pct"),
            "icu_rate_30d_pct": row.get("icu_rate_30d_pct"),
            "vaccinated_rate_30d_pct": row.get("vaccinated_rate_30d_pct"),
        }

    daily_df = sql.df(SQL_DAILY_30D_UF, params={"uf": uf}).rename(columns={"day": "x", "cases": "y"})
    monthly_df = sql.df(SQL_MONTHLY_12M_UF, params={"uf": uf}).rename(columns={"month": "x", "cases": "y"})

    return {"as_of": as_of, "kpis": kpi_payload, "daily_df": daily_df, "monthly_df": monthly_df}


# -----------------------------------------------------------------------------
# UI — header + sidebar
# -----------------------------------------------------------------------------

LOGO = PROJECT_ROOT / "assets" / "indicium_logo.png"

st.title("SRAG — Dashboard & Agente")
st.caption("Technical Case • Analytics + Intent-Routed Agent")

with st.sidebar:
    if LOGO.exists():
        st.image(str(LOGO), use_container_width=True)
    else:
        st.markdown("**Indicium**")

    st.header("Filtros")
    scope_label = st.radio("Escopo", ["Brasil", "UF"], horizontal=True)
    chosen_uf: Optional[str] = None
    if scope_label == "UF":
        brtmp = load_br_data()
        uf_opts = sorted(brtmp["top_ufs"]["uf"].unique().tolist())
        chosen_uf = st.selectbox("Selecione a UF", uf_opts, index=(uf_opts.index("SP") if "SP" in uf_opts else 0))

# -----------------------------------------------------------------------------
# Data binding (by scope)
# -----------------------------------------------------------------------------

if scope_label == "Brasil":
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
    top_ufs = pd.DataFrame()

st.caption(f"Data as of: **{as_of or 'n/a'}**")

# -----------------------------------------------------------------------------
# KPI row
# -----------------------------------------------------------------------------

c1, c2, c3, c4 = st.columns(4)
with c1:
    val = kpis.get("growth_7d_pct") if isinstance(kpis, dict) else kpis.growth_7d_pct
    kpi_card("Crescimento (7d vs 7 prev.)", val, fmt="pct")
with c2:
    val = kpis.get("cfr_closed_30d_pct") if isinstance(kpis, dict) else kpis.cfr_closed_30d_pct
    kpi_card("CFR (casos encerrados, 30d)", val, fmt="pct")
with c3:
    val = kpis.get("icu_rate_30d_pct") if isinstance(kpis, dict) else kpis.icu_rate_30d_pct
    kpi_card("% casos com UTI (30d)", val, fmt="pct")
with c4:
    val = kpis.get("vaccinated_rate_30d_pct") if isinstance(kpis, dict) else kpis.vaccinated_rate_30d_pct
    kpi_card("% casos com vacinação (30d)", val, fmt="pct")

# -----------------------------------------------------------------------------
# Charts
# -----------------------------------------------------------------------------

st.markdown("### Tendências")
lcol, rcol = st.columns(2)
with lcol:
    plot_line(daily_df, "Casos diários (últimos 30 dias)", "casos")
with rcol:
    plot_bar(monthly_df, "Casos mensais (últimos 12 meses)", "casos")

if scope_label == "Brasil":
    st.markdown("### UFs com mais casos (últimos 30 dias)")
    top_uf_bar(top_ufs, "Top UFs por casos (30d)")

st.divider()

# -----------------------------------------------------------------------------
# Agent chat — usa intent_router.handle()
# -----------------------------------------------------------------------------

st.subheader("🤖 Chat do Agente")

# estado de conversa
if "last_intent" not in st.session_state:
    st.session_state.last_intent: Optional[Intent] = None
if "messages" not in st.session_state:
    st.session_state.messages = []

# render histórico
for m in st.session_state.messages:
    st.chat_message(m["role"]).markdown(m["content"])

# user input
user_text = st.chat_input(
    placeholder=(
        "Pergunte algo… | Ex.: O que você pode fazer? • "
        "Quantas mortes ocorreram em SP nos últimos 30 dias • "
        "Quais as últimas notícias sobre SRAG em SC"
    )
)

if user_text:
    st.session_state.messages.append({"role": "user", "content": user_text})
    st.chat_message("user").markdown(user_text)

    try:
        reply_md, new_intent = agent_handle(user_text, previous_intent=st.session_state.last_intent)
        st.session_state.last_intent = new_intent  # mantém contexto para follow-ups
    except TypeError:
        # compat: intent_router antigo sem previous_intent
        reply_md, new_intent = agent_handle(user_text)
        st.session_state.last_intent = new_intent if isinstance(new_intent, Intent) else st.session_state.last_intent
    except Exception as exc:
        reply_md = f"Erro ao processar sua solicitação: `{exc}`"
        new_intent = None

    # resposta principal (markdown)
    st.session_state.messages.append({"role": "assistant", "content": reply_md})
    st.chat_message("assistant").markdown(reply_md)

    # Se for NLQUERY, renderize a tabela inteira (até 1000 linhas) e o SQL
    if isinstance(new_intent, Intent) and new_intent.kind == "nlquery":
        try:
            from case_indicium.agent.tools import query_nl
            df, sql_used = query_nl(user_text, max_rows=1000)
            st.caption("Resultado (até 1000 linhas):")
            st.dataframe(df, use_container_width=True)
            with st.expander("SQL gerado"):
                st.code(sql_used, language="sql")
        except Exception as exc:
            st.warning(f"Não consegui renderizar a tabela completa: {exc}")
