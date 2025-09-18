# src/case_indicium/agent/intent_router.py
"""
PT-first intent router for the SRAG agent (production-ready, LLM-first).

Goals
-----
- LLM-first routing: the model chooses the closest intent and extracts hints.
- Fallback to lightweight rules only if the LLM can't classify.
- Distinguish: greet | news | report | explain | dataqa | nlquery | trend | compare | chitchat | unknown.
- Extract: scope ('br'|'uf'), UF code, metric id, days_back window (1|7|30|90).
- Provide a single `handle()` entrypoint for the UI (Streamlit/CLI).

Environment
-----------
- OPENAI_API_KEY or GROQ_API_KEY: required for LLM routing.
- INTENT_USE_LLM=0 : disables LLM (rare, for offline dev). Defaults to enabled.

Notes
-----
- Metric ids align with metrics_registry.py: growth_7d | cfr_30d_closed | icu_rate_30d | vaccinated_rate_30d.
- `handle()` returns (markdown_reply, resolved_intent) so the UI can keep conversational context.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict, Tuple, List, Literal
import os
import re
import unicodedata

from pydantic import BaseModel, Field, ValidationError


# =============================================================================
# Public data model
# =============================================================================

@dataclass
class Intent:
    kind: str  # 'greet'|'news'|'report'|'explain'|'dataqa'|'nlquery'|'trend'|'compare'|'chitchat'|'unknown'
    metric: Optional[str] = None
    scope: Optional[str] = None   # 'br'|'uf'
    uf: Optional[str] = None
    confidence: float = 0.0
    days_back: Optional[int] = None


# =============================================================================
# Normalization helpers
# =============================================================================

def _normalize(s: str) -> str:
    """Lowercase, strip accents, collapse whitespace; keep alnum + spaces."""
    s = (s or "").lower().strip()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = re.sub(r"\s+", " ", s)
    return s


# =============================================================================
# LLM-first classifier
# =============================================================================

INTENT_USE_LLM = os.getenv("INTENT_USE_LLM", "1") != "0"  # default ON

class LLMIntent(BaseModel):
    kind: Literal["greet", "news", "report", "explain", "dataqa", "nlquery",
                  "trend", "compare", "chitchat", "unknown"]
    metric: str | None = None
    scope: Literal["br", "uf"] | None = None
    uf: str | None = None
    days_back: int | None = None
    confidence: float = Field(ge=0, le=1)


_LLM_SYSTEM = """Você é um roteador de intenções para um agente de SRAG (PT-BR).
Classifique a mensagem do usuário em EXATAMENTE um destes tipos:
greet | news | report | explain | dataqa | nlquery | trend | compare | chitchat | unknown.

Regras:
- Perguntas do tipo "quantos/qual o número/listar/contagem/total/somar/por UF/por mês/ordenado" → **nlquery**.
- Se for follow-up (ex.: "e no RJ?"), use previous_intent e o UF anterior.
- scope: "uf" quando houver UF explícita (sigla ou nome), senão "br".
- uf: sigla (SP,RJ,PE,...) quando identificável.
- metric (quando fizer sentido): growth_7d | cfr_30d_closed | icu_rate_30d | vaccinated_rate_30d.
- days_back: use 1 (hoje), 7, 30 ou 90 se o texto sugerir; caso contrário null.
- Se a mensagem for só conversa/amenidade, classifique como **chitchat**.

Responda APENAS JSON com: kind, metric, scope, uf, days_back, confidence.

Exemplos (saídas ilustrativas):

Usuário: "quantos óbitos no Brasil nos últimos 30 dias?"
→ {"kind":"nlquery","metric":null,"scope":"br","uf":null,"days_back":30,"confidence":0.85}

Usuário: "quantos casos em SP por dia na última semana?"
→ {"kind":"nlquery","metric":null,"scope":"uf","uf":"SP","days_back":7,"confidence":0.86}

Usuário: "gerar relatório padrão do RJ"
→ {"kind":"report","metric":null,"scope":"uf","uf":"RJ","days_back":null,"confidence":0.92}

Usuário: "o que é CFR?"
→ {"kind":"explain","metric":"cfr_30d_closed","scope":"br","uf":null,"days_back":null,"confidence":0.9}

Usuário: "tem novidades de SRAG em Pernambuco hoje?"
→ {"kind":"news","metric":null,"scope":"uf","uf":"PE","days_back":1,"confidence":0.8}
"""


def _llm_classify(user_text: str, previous_intent: Intent | None) -> Intent:
    """Ask the LLM to classify intent; return Intent object (or unknown)."""
    from .llm_router import generate_text

    ctx = {
        "kind": (previous_intent.kind if previous_intent else None),
        "scope": (previous_intent.scope if previous_intent else None),
        "uf": (previous_intent.uf if previous_intent else None),
        "metric": (previous_intent.metric if previous_intent else None),
        "days_back": (previous_intent.days_back if previous_intent else None),
    }
    user_payload = (
        "Mensagem do usuário (PT-BR):\n"
        f"{user_text}\n\n"
        "previous_intent (pode ser null):\n"
        f"{ctx}\n"
        "Responda apenas JSON."
    )
    raw = generate_text(user_payload, _LLM_SYSTEM, temperature=0.0, max_tokens=320)

    try:
        data = LLMIntent.model_validate_json(raw).model_dump()
    except ValidationError:
        # Best-effort: try to parse as dict
        try:
            import json
            data = LLMIntent.model_validate(json.loads(raw)).model_dump()
        except Exception:
            return Intent(kind="unknown", confidence=0.0)

    return Intent(
        kind=data["kind"],
        metric=data.get("metric"),
        scope=data.get("scope"),
        uf=data.get("uf"),
        days_back=data.get("days_back"),
        confidence=float(data.get("confidence", 0.6)),
    )


# =============================================================================
# Lightweight fallback (rules) — only used if LLM is off/failed/unknown
# =============================================================================

_UF_BY_NAME: Dict[str, str] = {
    "acre": "AC", "alagoas": "AL", "amapa": "AP", "amazonas": "AM", "bahia": "BA",
    "ceara": "CE", "distrito federal": "DF", "espirito santo": "ES", "goias": "GO",
    "maranhao": "MA", "mato grosso": "MT", "mato grosso do sul": "MS", "minas gerais": "MG",
    "para": "PA", "paraiba": "PB", "parana": "PR", "pernambuco": "PE", "piaui": "PI",
    "rio de janeiro": "RJ", "rio grande do norte": "RN", "rio grande do sul": "RS",
    "rondonia": "RO", "roraima": "RR", "santa catarina": "SC", "sao paulo": "SP",
    "sergipe": "SE", "tocantins": "TO",
}
_UF_CODES = set(_UF_BY_NAME.values())

def _detect_uf_and_scope(orig_text: str) -> Tuple[str, Optional[str]]:
    """Return ('uf'|'br', UF_CODE|None) scanning sigla or full name."""
    m = re.search(r"\b([A-Z]{2})\b", orig_text or "")
    if m and m.group(1) in _UF_CODES:
        return "uf", m.group(1)
    t = _normalize(orig_text)
    for name, code in _UF_BY_NAME.items():
        if re.search(rf"\b{name}\b", t):
            return "uf", code
    return "br", None

_METRIC_ALIASES: Dict[str, str] = {
    "taxa de aumento": "growth_7d",
    "crescimento 7d": "growth_7d",
    "aumento 7 dias": "growth_7d",
    "growth": "growth_7d",
    "cfr": "cfr_30d_closed",
    "crf": "cfr_30d_closed",
    "case fatality rate": "cfr_30d_closed",
    "taxa de letalidade": "cfr_30d_closed",
    "letalidade": "cfr_30d_closed",
    "taxa de mortalidade de casos": "cfr_30d_closed",
    "uti": "icu_rate_30d",
    "taxa de uti": "icu_rate_30d",
    "icu rate": "icu_rate_30d",
    "percentual de casos com uti": "icu_rate_30d",
    "internacao em uti": "icu_rate_30d",
    "admissao em uti": "icu_rate_30d",
    "taxa de vacinacao": "vaccinated_rate_30d",
    "taxa de vacinados": "vaccinated_rate_30d",
    "percentual de vacinados": "vaccinated_rate_30d",
    "vaccinated rate": "vaccinated_rate_30d",
}

def _detect_metric(t_norm: str) -> Optional[str]:
    """Phrase-first; fallback token check for cfr/crf."""
    for k, mid in sorted(_METRIC_ALIASES.items(), key=lambda x: -len(x[0])):
        if k in t_norm:
            return mid
    tokens = t_norm.split()
    if "cfr" in tokens or "crf" in tokens:
        return "cfr_30d_closed"
    return None

def parse_days_back(text: str) -> int:
    """Extract a sensible days_back from natural PT; default 14."""
    t = _normalize(text)
    if any(k in t for k in ("hoje", "agora")):
        return 1
    if "ontem" in t:
        return 2
    if re.search(r"\b(7|sete)\b.*\bdias\b", t) or "semana" in t:
        return 7
    if re.search(r"\b(30|trinta)\b.*\bdias\b", t) or any(k in t for k in ("mes", "mês")):
        return 30
    if re.search(r"\b(90|noventa)\b.*\bdias\b", t) or "trimestre" in t:
        return 90
    return 14

# very small rule set used *only* as safety net
_RULES: Dict[str, List[str]] = {
    "greet": [r"\b(oi|ola|ol[aá])\b", r"\b(bom dia|boa tarde|boa noite)\b"],
    "news": [r"\bnoticia[s]?\b", r"\bnovidade[s]?\b", r"\bultimas? noticia[s]?\b"],
    "report": [r"\brelat[oó]rio\b", r"\breport\b", r"\bsum[aá]rio\b"],
    "explain": [r"\bexplicar\b", r"\bo que (e|é|eh)\b", r"\bdefini(c|ç)[aã]o\b"],
    "trend": [r"\btend[eê]ncia[s]?\b", r"\bevolu[cç][aã]o\b"],
    "compare": [r"\bcompar(ar|e)\b", r"\branking\b"],
}

def _score_intents_rules(t_norm: str) -> Intent:
    """Minimal rule classifier used only as last resort."""
    scope, uf = _detect_uf_and_scope(t_norm)
    metric = _detect_metric(t_norm)
    hits: Dict[str, int] = {k: 0 for k in _RULES}
    for kind, pats in _RULES.items():
        for p in pats:
            if re.search(p, t_norm):
                hits[kind] += 1
    best, score = "unknown", 0
    for k in ["greet", "news", "report", "explain", "trend", "compare"]:
        if hits.get(k, 0) > score:
            best, score = k, hits[k]
    conf = 1.0 if score > 0 else 0.0
    return Intent(
        kind=best, metric=metric, scope=scope, uf=uf,
        days_back=parse_days_back(t_norm), confidence=conf
    )


# =============================================================================
# Public API
# =============================================================================

def classify(text: str, previous_intent: Intent | None = None) -> Intent:
    """
    LLM-first classification with a tiny rule-based fallback.
    """
    orig = text or ""
    # 1) LLM path
    if INTENT_USE_LLM and (os.getenv("OPENAI_API_KEY") or os.getenv("GROQ_API_KEY")):
        it = _llm_classify(orig, previous_intent)
        if it.kind != "unknown":
            return it
    # 2) Fallback rules
    return _score_intents_rules(_normalize(orig))


def extract_explain_term(text: str) -> str:
    """
    Extract term after 'explicar/explica/o que e/é/eh'; fallback: last clause.
    """
    t = (text or "").strip()
    t_norm = _normalize(t)
    for trigger in ("explicar", "explica", "o que e", "o que eh", "o que é"):
        if t_norm.startswith(trigger):
            cand = t[len(trigger):].strip(" :?.,;")
            return cand if cand else t
    tokens = re.split(r"[?.,;:]", t.strip())
    return (tokens[-1] or t).strip()


def greet_message() -> str:
    """Short self-introduction for greet intent (Markdown)."""
    return (
        "Olá! 👋 Eu sou o agente SRAG. Posso:\n"
        "- 📰 Trazer **notícias recentes** (com links)\n"
        "- 📊 Gerar o **relatório padrão** (Brasil ou por **UF**)\n"
        "- 📖 **Explicar** métricas/termos\n"
        "- 🧠 Responder **perguntas sobre o dicionário de dados**\n"
        "- 🔎 Fazer **consulta em linguagem natural → SQL** (segura)\n"
        "- 📈 Comentar **tendências** (7d/30d/12m)\n\n"
        "Como posso ajudar agora?"
    )


# =============================================================================
# Unified handler for the UI (returns reply + resolved intent)
# =============================================================================

def handle(user_text: str, previous_intent: Intent | None = None) -> tuple[str, Intent]:
    """
    Routes the user text to the right feature and returns Markdown + Intent.
    """
    it = classify(user_text, previous_intent=previous_intent)
        # --- Heurística: se o usuário pede número/contagem/listagem, force nlquery ---
    tnorm = (user_text or "").lower()
    looks_countish = any(k in tnorm for k in [
        "quantos", "quantas", "número de", "numero de",
        "total de", "contagem", "somar", "listar", "listagem",
        "por uf", "por estado", "por mês", "por mes", "agrupado"
    ])
    # se a LLM devolveu report/explain/chitchat por engano, puxe para nlquery
    if looks_countish and it.kind in {"report", "explain", "chitchat", "unknown"}:
        it.kind = "nlquery"

    # 1) Greeting
    if it.kind == "greet":
        return greet_message(), it

    # 2) News (with links)
    if it.kind == "news":
        from .news_client import fetch_recent_news_srag, summarize_news_items
        extra = f"Brasil {it.uf}" if it.uf else "Brasil"
        items = fetch_recent_news_srag(limit=8, days_back=it.days_back or 14, query=extra)
        if not items:
            return (
                "Não encontrei notícias recentes de SRAG com esses filtros. "
                "Você quer ampliar para **30 dias** ou focar em alguma **UF**?",
                it,
            )
        return summarize_news_items(items, max_items=8), it

    # 3) Explain (glossary)
    if it.kind == "explain":
        from .tools import glossary_lookup
        term = extract_explain_term(user_text)
        return f"**{term}** — {glossary_lookup(term)}", it

    # 4) Data QA (schema / dictionary questions answered by LLM)
    if it.kind == "dataqa":
        try:
            from .tools import answer_data_question
            ans = answer_data_question(user_text, max_tokens=700)
            return ans, it
        except Exception as exc:
            return f"Não consegui responder com base no dicionário de dados agora: `{exc}`", it

    # 5) NL → SQL (safe) + execution
    if it.kind == "nlquery":
        try:
            from .tools import query_nl
            df, sql_used = query_nl(user_text, max_rows=500)
            head_md = df.head(15).to_markdown(index=False) if not df.empty else "_(sem linhas)_"
            md = (
                "### Consulta (NL→SQL)\n"
                f"```sql\n{sql_used}\n```\n\n"
                "Prévia (até 15 linhas):\n\n"
                f"{head_md}"
            )
            return md, it
        except Exception as exc:
            return (
                "Não consegui executar a consulta em linguagem natural. "
                f"Pode reformular em uma frase simples? Detalhe **o que**, **onde** (UF/BR) e **período**.\n\n"
                f"Erro técnico: `{exc}`",
                it,
            )

    # 6) Report
    if it.kind == "report":
        from .generator import build_report
        from .schemas import ReportInput
        scope = "uf" if it.uf else "br"
        out = build_report(ReportInput(scope=scope, uf=it.uf))
        return out.report_md, it

    # 7) Trend (quick text)
    if it.kind == "trend":
        from .tools import get_series
        scope = "uf" if it.uf else "br"
        series = get_series(scope=scope, uf=it.uf)
        daily = series.get("daily")
        if daily is None or len(daily) < 2:
            where = f"**{it.uf}**" if it.uf else "**Brasil**"
            return f"Sem dados suficientes para tendência em {where}.", it
        if len(daily) >= 14:
            last_7 = float(daily.tail(7)["y"].sum())
            prev_7 = float(daily.tail(14).head(7)["y"].sum())
            trend_7d = None if prev_7 == 0 else 100.0 * (last_7 - prev_7) / prev_7
        else:
            trend_7d = None
        where = f"**{it.uf}**" if it.uf else "**Brasil**"
        pct = "indisponível" if trend_7d is None else f"{trend_7d:.1f}%"
        msg = f"**Tendência (últimos 7 vs. 7 anteriores)** em {where}: {pct}.\nPontos diários: **{len(daily)}**."
        return msg, it

    # 8) Compare (placeholder)
    if it.kind == "compare":
        return ("Comparações/rankings ainda não estão plugados. "
                "Quer comparar por **casos (30d)**, **UTI%** ou **CFR**?"), it

    # 9) Chitchat (LLM small talk)
    if it.kind == "chitchat":
        from .llm_router import generate_text
        sys = ("Você é um assistente PT-BR do projeto SRAG. "
               "Responda de forma breve e útil. Não invente números epidemiológicos; "
               "se pedirem dados, sugira usar relatório ou consulta.")
        txt = generate_text(user_text, sys, temperature=0.3, max_tokens=300)
        return txt, it

    # 10) Fallback — ask for details
    ask = (
        "Não entendi bem o que você precisa. Você quer **notícias**, **relatório**, "
        "**explicação** de um termo, **consulta por linguagem natural** (SQL), "
        "**tendências** ou **comparar** UFs?\n\n"
        "Exemplos:\n"
        "- *tem novidades de SRAG em Pernambuco?*\n"
        "- *gerar relatório padrão do RJ*\n"
        "- *o que é CFR?*\n"
        "- *listar casos por UF nos últimos 30 dias*"
    )
    return ask, it


# =============================================================================
# Manual test
# =============================================================================

if __name__ == "__main__":
    samples = [
        "oi, tudo bem? o que você faz?",
        "quero as últimas notícias de SRAG no Brasil",
        "tem novidades de SRAG no Brasil hoje?",
        "e no RJ?",
        "gerar relatório padrão do RJ",
        "me explique sobre CFR",
        "como é a tabela? quais colunas existem?",
        "lista casos por UF nos últimos 30 dias",
        "tendência nos últimos 30 dias",
        "qual modelo você usa?",
        "SRAG",
    ]
    prev = None
    for s in samples:
        reply, prev = handle(s, previous_intent=prev)
        print(f"\n> {s}\n{reply}\nintent={prev}")
