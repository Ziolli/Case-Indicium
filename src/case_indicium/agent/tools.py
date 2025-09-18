# src/case_indicium/agent/tools.py
"""Agent tools: PT-grounded schema, data Q&A, and NL→SQL (guarded) for gold facts.

Docstrings/comments in English (as requested).
LLM-facing prompts + data dictionary in Portuguese for better comprehension.

Key functions
-------------
- build_schema_snapshot(): PT snapshot of gold tables + metrics + whitelist.
- answer_data_question(): LLM answers using ONLY the snapshot context.
- nl_to_sql(): NL (PT) → safe DuckDB SELECT SQL (only gold tables/columns).
- run_sql_text_safe(): executes read-only SELECT with whitelist + LIMIT.
- query_nl(): high-level (NL → SQL → DataFrame, returns (df, sql_used)).

Env (optional)
--------------
- GOLD_DAILY_TABLE=gold.fct_daily_uf
- GOLD_MONTHLY_TABLE=gold.fct_monthly_uf
- OPENAI_API_KEY or GROQ_API_KEY for llm_router.generate_text()
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import os
import re
import textwrap
import pandas as pd

from .sql_client import SQLClient
from .llm_router import generate_text

# If you keep a metrics registry, we merge it; otherwise keep empty.
try:
    from .metrics_registry import METRICS
    _METRICS_DICT = {k: v.model_dump() for k, v in METRICS.items()}
except Exception:
    _METRICS_DICT = {}

# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------

GOLD_DAILY = os.getenv("GOLD_DAILY_TABLE", "gold.fct_daily_uf")
GOLD_MONTHLY = os.getenv("GOLD_MONTHLY_TABLE", "gold.fct_monthly_uf")
_ALLOWED_TABLES = [GOLD_DAILY, GOLD_MONTHLY]


# -----------------------------------------------------------------------------
# Static Data Dictionary (Portuguese) for gold tables
# -----------------------------------------------------------------------------

# NOTE: keep aligned to your ETL / samples you provided.
# These descriptions are what the LLM will read to understand each field.

_STATIC_TABLES_PT: List[Dict[str, Any]] = [
    {
        "name": GOLD_DAILY,
        "desc": (
            "Fato diário por UF. Uma linha por (dia, uf). Métricas já agregadas no nível diário."
        ),
        "columns": [
            {"name": "day",                         "type": "DATE",        "desc": "Data (dia, ISO)."},
            {"name": "uf",                          "type": "VARCHAR(2)",  "desc": "UF (sigla de 2 letras)."},
            {"name": "cases",                       "type": "INTEGER",     "desc": "Casos notificados no dia."},
            {"name": "deaths",                      "type": "INTEGER",     "desc": "Óbitos do dia."},
            {"name": "icu_cases",                   "type": "INTEGER",     "desc": "Casos com passagem por UTI no dia."},
            {"name": "vaccinated_cases",            "type": "INTEGER",     "desc": "Casos com registro de vacinação no dia."},
            {"name": "pending_60d_cases",           "type": "INTEGER",     "desc": "Casos pendentes (estimativa) após 60 dias."},
            {"name": "closed_cases_30d",            "type": "INTEGER",     "desc": "Casos encerrados (coorte de 30 dias)."},
            {"name": "deaths_30d",                  "type": "INTEGER",     "desc": "Óbitos em coorte de 30 dias."},
            {"name": "median_symptom_to_notification_days", "type": "FLOAT", "desc": "Mediana (dias) do início dos sintomas até a notificação."},
            {"name": "median_icu_los_days",         "type": "FLOAT",       "desc": "Mediana (dias) de permanência em UTI."},
            {"name": "cfr_closed_30d_pct",          "type": "FLOAT (0–100)","desc": "Letalidade % entre casos encerrados (coorte 30d)."},
            {"name": "icu_rate_pct",                "type": "FLOAT (0–100)","desc": "% de casos com UTI (no dia). Não é ocupação de leito."},
            {"name": "vaccinated_rate_pct",         "type": "FLOAT (0–100)","desc": "% de casos com registro de vacinação (no dia)."},
            {"name": "pending_60d_pct",             "type": "FLOAT (0–100)","desc": "% de casos pendentes após 60 dias (estimado)."},
            {"name": "cases_ma7",                   "type": "FLOAT",       "desc": "Média móvel (7 dias) de casos."},
            {"name": "deaths_ma7",                  "type": "FLOAT",       "desc": "Média móvel (7 dias) de óbitos."},
        ],
    },
    {
        "name": GOLD_MONTHLY,
        "desc": (
            "Fato mensal por UF. Uma linha por (mês, uf). Métricas agregadas ao nível do mês."
        ),
        "columns": [
            {"name": "month",                       "type": "DATE (1º dia)","desc": "Mês (primeiro dia do mês)."},
            {"name": "uf",                          "type": "VARCHAR(2)",   "desc": "UF (sigla de 2 letras)."},
            {"name": "cases",                       "type": "INTEGER",      "desc": "Casos notificados no mês."},
            {"name": "deaths",                      "type": "INTEGER",      "desc": "Óbitos no mês."},
            {"name": "icu_cases",                   "type": "INTEGER",      "desc": "Casos com passagem por UTI no mês."},
            {"name": "vaccinated_cases",            "type": "INTEGER",      "desc": "Casos com registro de vacinação no mês."},
            {"name": "pending_60d_cases",           "type": "INTEGER",      "desc": "Casos pendentes (estimativa) após 60 dias."},
            {"name": "closed_cases_30d",            "type": "INTEGER",      "desc": "Casos encerrados (coorte de 30 dias)."},
            {"name": "deaths_30d",                  "type": "INTEGER",      "desc": "Óbitos em coorte de 30 dias."},
            {"name": "median_symptom_to_notification_days", "type": "FLOAT","desc": "Mediana (dias) do início dos sintomas até a notificação."},
            {"name": "median_icu_los_days",         "type": "FLOAT",        "desc": "Mediana (dias) de permanência em UTI."},
            {"name": "cfr_closed_30d_pct",          "type": "FLOAT (0–100)","desc": "Letalidade % entre casos encerrados (coorte 30d)."},
            {"name": "icu_rate_pct",                "type": "FLOAT (0–100)","desc": "% de casos com UTI (no mês)."},
            {"name": "vaccinated_rate_pct",         "type": "FLOAT (0–100)","desc": "% de casos com registro de vacinação (no mês)."},
            {"name": "pending_60d_pct",             "type": "FLOAT (0–100)","desc": "% de casos pendentes após 60 dias (estimado)."},
        ],
    },
]

_STATIC_METRICS_PT: Dict[str, Dict[str, Any]] = {
    # Merges your registry if present (keeps other parts of the app working).
    **_METRICS_DICT
}


# -----------------------------------------------------------------------------
# Snapshot + prompt rendering
# -----------------------------------------------------------------------------

def build_schema_snapshot() -> Dict[str, Any]:
    """Return PT snapshot used to ground LLM prompts (gold tables only)."""
    tables = list(_STATIC_TABLES_PT)
    allowed = [t["name"] for t in tables] or list(_ALLOWED_TABLES)
    return {"tables": tables, "metrics": _STATIC_METRICS_PT, "allowed_tables": allowed}


def _render_schema_for_prompt(snapshot: Dict[str, Any], max_cols: int = 500) -> str:
    """Render a compact PT context string for the LLM."""
    lines: List[str] = []
    lines.append("=== TABELAS DISPONÍVEIS (GOLD) ===")
    col_count = 0
    for t in snapshot["tables"]:
        lines.append(f"- {t['name']}: {t.get('desc','')}")
        for c in t["columns"]:
            desc = f" — {c.get('desc','')}" if c.get('desc') else ""
            lines.append(f"  • {c['name']} :: {c['type']}{desc}")
            col_count += 1
            if col_count >= max_cols:
                lines.append("  • ... (truncado)")
                break
        if col_count >= max_cols:
            break

    if snapshot.get("metrics"):
        lines.append("\n=== MÉTRICAS CONCEITUAIS (se aplicável) ===")
        for mid, m in snapshot["metrics"].items():
            label = m.get("label") or mid
            unit = m.get("unit", "-")
            window = m.get("window", "-")
            scope = ",".join(m.get("scope", [])) if isinstance(m.get("scope"), list) else str(m.get("scope", ""))
            lines.append(f"- {mid} | label={label} | unidade={unit} | janela={window} | escopo={scope}")
    return "\n".join(lines)


# -----------------------------------------------------------------------------
# Safe SQL execution (read-only)
# -----------------------------------------------------------------------------

_SQL_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|CREATE|DROP|ALTER|TRUNCATE|ATTACH|DETACH|COPY|REPLACE|GRANT|REVOKE)\b",
    re.IGNORECASE,
)

def _extract_tables_from_sql(sql: str) -> List[str]:
    """Naive FROM/JOIN table extractor for whitelist checks."""
    pats = [r"\bFROM\s+([a-zA-Z0-9_\.]+)", r"\bJOIN\s+([a-zA-Z0-9_\.]+)"]
    tables: List[str] = []
    for p in pats:
        for m in re.finditer(p, sql, flags=re.IGNORECASE):
            tables.append(m.group(1))
    # de-dup preserving order
    seen, out = set(), []
    for t in tables:
        if t not in seen:
            out.append(t)
            seen.add(t)
    return out


def run_sql_text_safe(sql: str, *, max_rows: int = 500, allowed_tables: Optional[List[str]] = None) -> pd.DataFrame:
    """Execute a *read-only* SELECT with whitelist + LIMIT enforcement."""
    clean = sql.strip().rstrip(";")

    if not re.match(r"^\s*SELECT\b", clean, flags=re.IGNORECASE):
        raise ValueError("Somente SELECT é permitido.")

    if _SQL_FORBIDDEN.search(clean):
        raise ValueError("Palavra-chave SQL proibida detectada.")

    used_tables = _extract_tables_from_sql(clean)
    if allowed_tables:
        for t in used_tables:
            if t not in allowed_tables:
                raise ValueError(f"Tabela não permitida neste contexto: {t}")

    # LIMIT
    if re.search(r"\bLIMIT\s+\d+\b", clean, flags=re.IGNORECASE):
        clean = re.sub(
            r"\bLIMIT\s+(\d+)\b",
            lambda m: f"LIMIT {min(int(m.group(1)), max_rows)}",
            clean,
            flags=re.IGNORECASE,
        )
    else:
        clean = f"{clean} LIMIT {max_rows}"

    client = SQLClient()
    return client.df(clean)


# -----------------------------------------------------------------------------
# NL → SQL with guardrails (LLM)
# -----------------------------------------------------------------------------

_SYSTEM_NL2SQL = """Você é um tradutor de linguagem natural → SQL para DuckDB (PT-BR).

Regras:
- Gere APENAS uma query SQL DuckDB válida começando com SELECT.
- Use SOMENTE as tabelas/colunas listadas no contexto.
- Inclua sempre LIMIT razoável (ex.: 200).
- Não faça DDL/DML nem use extensões externas.
- IMPORTANTE: quando o usuário pedir totais em uma janela (ex.: "últimos 30 dias"),
  **some as medidas base diárias** (`cases`, `deaths`, `icu_cases`, `vaccinated_cases`)
  sobre o período. NÃO some colunas já janeladas como `*_30d` ao longo de várias datas,
  pois isso superconta. As colunas `*_30d` representam janelas já agregadas e devem ser
  usadas isoladamente (ex.: último dia), não somadas em múltiplos dias.
""".format(daily=GOLD_DAILY, monthly=GOLD_MONTHLY)


def nl_to_sql(question_pt: str, snapshot: Optional[Dict[str, Any]] = None, *, default_limit: int = 200) -> str:
    """Translate a PT question into a safe DuckDB SELECT SQL (gold tables only)."""
    snapshot = snapshot or build_schema_snapshot()
    ctx = _render_schema_for_prompt(snapshot)

    user = textwrap.dedent(f"""
    CONTEXTO — Dicionário de dados (GOLD) e tabelas permitidas:
    {ctx}

    Pergunta do usuário (PT-BR):
    {question_pt}

    Requisito: retorne **APENAS** o SQL (uma ou mais linhas), sem comentários.
    Se for impossível responder com as tabelas/colunas listadas, retorne:
    SELECT 'indisponivel' AS motivo;
    """).strip()

    sql = generate_text(user, _SYSTEM_NL2SQL, temperature=0.0, max_tokens=400).strip()
    if not re.search(r"\bLIMIT\s+\d+\b", sql, flags=re.IGNORECASE):
        sql = f"{sql.rstrip(';')} LIMIT {default_limit}"
    return sql


def query_nl(question_pt: str, *, max_rows: int = 500) -> Tuple[pd.DataFrame, str]:
    """High-level: NL → SQL (LLM) → safe execution on GOLD tables."""
    snapshot = build_schema_snapshot()
    sql = nl_to_sql(question_pt, snapshot=snapshot, default_limit=min(max_rows, 200))
    df = run_sql_text_safe(sql, max_rows=max_rows, allowed_tables=snapshot["allowed_tables"])
    return df, sql


# -----------------------------------------------------------------------------
# Data dictionary Q&A (LLM grounded in PT schema)
# -----------------------------------------------------------------------------

_SYSTEM_DATA_QA = """Você é um assistente de documentação de dados (PT-BR).

Responda **somente** com base no contexto fornecido (tabelas/colunas/métricas).
- Não invente colunas, tabelas ou métricas.
- Se não souber, responda: "não documentado no dicionário".
- Quando citar campos, prefira `tabela.coluna`.
- Seja conciso e objetivo (2–6 linhas).
"""

def answer_data_question(question_pt: str, *, max_tokens: int = 700) -> str:
    """Answer data questions using ONLY the static PT dictionary snapshot (gold)."""
    snapshot = build_schema_snapshot()
    ctx = _render_schema_for_prompt(snapshot)
    user = f"Contexto de dados (GOLD):\n{ctx}\n\nPergunta do usuário (PT-BR):\n{question_pt}"
    return generate_text(user, _SYSTEM_DATA_QA, temperature=0.0, max_tokens=max_tokens)
