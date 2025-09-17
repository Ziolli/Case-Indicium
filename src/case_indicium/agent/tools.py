# src/case_indicium/agent/tools.py
"""Agent tools (safe, whitelisted). Ready for MCP exposure later.

- Glossary lookup in PT-BR with aliases + fuzzy matching
- Whitelisted SQL execution (no arbitrary SQL)
- KPI and time-series helpers for BR/UF scopes
"""

from __future__ import annotations

from typing import Any, Dict, Optional
import re
import unicodedata
from difflib import get_close_matches

import pandas as pd

from .sql_client import SQLClient
from . import queries as Q


# -----------------------------------------------------------------------------
# Glossary (PT-BR) — canonical entries (columns + derived metrics)
# -----------------------------------------------------------------------------

def _normalize_text(s: str) -> str:
    """Lowercase, strip accents, keep alphanum/spaces for robust matching."""
    s = s or ""
    s = s.lower().strip()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")  # remove accents
    s = re.sub(r"[^a-z0-9\s._-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


GLOSSARY_PT: Dict[str, str] = {
    # --- Derived metrics ---
    "growth_7d": (
        "Taxa de aumento de casos (7 dias): variação percentual dos últimos 7 dias "
        "em relação aos 7 dias anteriores, ancorada na data de corte (as_of). "
        "Se o período anterior tiver 0 casos, o crescimento é 'indisponível'."
    ),
    "cfr_30d_closed": (
        "CFR (30 dias, casos encerrados): óbitos divididos por casos encerrados nos "
        "últimos 30 dias, em %. Não é taxa de mortalidade populacional."
    ),
    "icu_rate_30d": (
        "% de casos com UTI (30 dias): percentual de casos que tiveram passagem por UTI "
        "nos últimos 30 dias. Não representa ocupação de leitos hospitalares."
    ),
    "vaccinated_rate_30d": (
        "% de casos vacinados (30 dias): percentual de casos com vacinação registrada "
        "nos últimos 30 dias. Não é cobertura vacinal da população."
    ),

    # --- Core columns from Silver ---
    "dt_notific": "Data de notificação do caso (DATE).",
    "dt_sin_pri": "Data de início dos sintomas (DATE).",
    "dt_evoluca": "Data do desfecho (alta ou óbito), pode ser nula (DATE).",
    "dt_encerra": "Data de encerramento do caso no sistema (DATE).",
    "sem_not": "Semana epidemiológica da notificação (INTEGER).",
    "evolucao_code": "Código do desfecho {1=CURA, 2=ÓBITO, 3=ÓBITO OUTRAS, 9=IGNORADO}.",
    "evolucao_label": "Rótulo do desfecho a partir de 'evolucao_code'.",
    "classi_fin": "Classificação final (etiologia) do caso.",
    "uti_bool": "Indicador de passagem por UTI (BOOLEAN).",
    "vacinado_bool": "Indicador de vacinação registrada no caso (BOOLEAN).",
    "idade": "Idade em anos (INTEGER).",
    "faixa_etaria": "Faixa etária derivada da idade (0–4, 5–17, 18–39, 40–59, 60+).",
    "sexo": "Sexo (M/F/...).",
    "uf": "UF de notificação (sigla de 2 letras).",
    "is_obito": "Flag para óbito (evolucao_code = 2).",
    "pendente_60d": "Provável pendência após 60 dias sem desfecho/encerramento (BOOLEAN).",
}

# Aliases/sinônimos → canonical key
ALIASES_PT: Dict[str, str] = {
    # CFR
    "cfr": "cfr_30d_closed",
    "crf": "cfr_30d_closed",
    "case fatality rate": "cfr_30d_closed",
    "taxa de letalidade": "cfr_30d_closed",
    "letalidade": "cfr_30d_closed",
    "taxa de mortalidade de casos": "cfr_30d_closed",

    # ICU rate
    "icu": "icu_rate_30d",
    "icu rate": "icu_rate_30d",
    "taxa de uti": "icu_rate_30d",
    "percentual de casos com uti": "icu_rate_30d",
    "uti": "icu_rate_30d",
    "internacao em uti": "icu_rate_30d",
    "admissao em uti": "icu_rate_30d",

    # Vaccinated rate
    "taxa de vacinacao": "vaccinated_rate_30d",
    "taxa de vacinados": "vaccinated_rate_30d",
    "percentual de vacinados": "vaccinated_rate_30d",
    "vaccinated rate": "vaccinated_rate_30d",

    # Growth
    "taxa de aumento": "growth_7d",
    "crescimento 7d": "growth_7d",
    "aumento 7 dias": "growth_7d",
}


def glossary_lookup(term: str) -> str:
    """Return PT-BR description for a data term, with alias + fuzzy fallback."""
    raw = (term or "").strip()
    if not raw:
        return "Informe o termo que deseja explicar."

    t = _normalize_text(raw)

    # Alias exact
    if t in ALIASES_PT:
        key = ALIASES_PT[t]
        return GLOSSARY_PT.get(key, f"Termo mapeado para '{key}', mas sem descrição.")

    # Exact canonical
    if t in GLOSSARY_PT:
        return GLOSSARY_PT[t]

    # Fuzzy over aliases + canonical keys
    candidates = list(GLOSSARY_PT.keys()) + list(ALIASES_PT.keys())
    match = get_close_matches(t, candidates, n=1, cutoff=0.66)
    if match:
        m = match[0]
        key = ALIASES_PT.get(m, m)
        if key in GLOSSARY_PT:
            return f"{GLOSSARY_PT[key]} *(interpretei como '{m}')*"

    return "Termo não encontrado no glossário do projeto."


# -----------------------------------------------------------------------------
# SQL (whitelisted) helpers
# -----------------------------------------------------------------------------

def run_sql_whitelisted(query_name: str, params: Optional[Dict[str, Any]] = None, limit: int = 500) -> pd.DataFrame:
    """Run a whitelisted query by symbolic name defined in queries.py."""
    if not hasattr(Q, query_name):
        raise KeyError(f"Unknown whitelisted query: {query_name}")
    sql = getattr(Q, query_name)
    client = SQLClient()
    df = client.df(sql, params=params or {})
    if limit and len(df) > limit:
        df = df.head(limit)
    return df


def get_kpis(scope: str = "br", uf: Optional[str] = None) -> Dict[str, Any]:
    """Return KPIs for last 30d window and 7d growth. PT-BR keys for UI/LLM payloads."""
    res: Dict[str, Any] = {}

    # Growth 7d
    if scope == "br":
        df_g = run_sql_whitelisted("SQL_GROWTH_7D_BR")
    else:
        df_g = run_sql_whitelisted("SQL_GROWTH_7D_UF", params={"uf": uf})
    if not df_g.empty:
        row = df_g.iloc[0]
        res["cases_7d"] = float(row.get("cases_7d") or 0)
        res["cases_prev_7d"] = float(row.get("cases_prev_7d") or 0)
        res["growth_7d_pct"] = None if row.get("growth_7d_pct") is None else float(row.get("growth_7d_pct"))

    # 30d KPIs
    if scope == "br":
        df_k = run_sql_whitelisted("SQL_KPIS_30D_BR")
    else:
        df_k = run_sql_whitelisted("SQL_KPIS_30D_UF", params={"uf": uf})
    if not df_k.empty:
        row = df_k.iloc[0]
        res.update({
            "cases_30d": float(row.get("cases_30d") or 0),
            "icu_cases_30d": float(row.get("icu_cases_30d") or 0),
            "vaccinated_cases_30d": float(row.get("vaccinated_cases_30d") or 0),
            "closed_cases_30d": float(row.get("closed_cases_30d") or 0),
            "deaths_30d": float(row.get("deaths_30d") or 0),
            "cfr_closed_30d_pct": (float(row["cfr_closed_30d_pct"]) if row["cfr_closed_30d_pct"] is not None else None),
            "icu_rate_30d_pct": (float(row["icu_rate_30d_pct"]) if row["icu_rate_30d_pct"] is not None else None),
            "vaccinated_rate_30d_pct": (float(row["vaccinated_rate_30d_pct"]) if row["vaccinated_rate_30d_pct"] is not None else None),
        })
    return res


def get_series(scope: str = "br", uf: Optional[str] = None) -> Dict[str, pd.DataFrame]:
    """Return daily (30d) and monthly (12m) series as DataFrames with columns x,y."""
    if scope == "br":
        daily = run_sql_whitelisted("SQL_DAILY_30D_BR")
        monthly = run_sql_whitelisted("SQL_MONTHLY_12M_BR")
    else:
        daily = run_sql_whitelisted("SQL_DAILY_30D_UF", params={"uf": uf})
        monthly = run_sql_whitelisted("SQL_MONTHLY_12M_UF", params={"uf": uf})
    return {
        "daily": daily.rename(columns={"day": "x", "cases": "y"}),
        "monthly": monthly.rename(columns={"month": "x", "cases": "y"}),
    }


__all__ = [
    "glossary_lookup",
    "run_sql_whitelisted",
    "get_kpis",
    "get_series",
]
