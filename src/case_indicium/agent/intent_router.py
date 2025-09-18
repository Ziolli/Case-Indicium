# src/case_indicium/agent/intent_router.py
"""
PT-first intent router for the SRAG agent (production-ready).

Goals
-----
- Rule-first (fast) + LLM fallback when confidence is low or text looks like follow-up.
- Distinguish: greet | news | report | explain | trend | compare | unknown.
- Extract: scope ('br'|'uf'), UF code, metric id, confidence (0..1), days_back window.
- Provide a single `handle()` entrypoint for the UI (Streamlit/CLI).

Environment
-----------
- INTENT_USE_LLM=1  → always try LLM fallback (helpful during testing)
- OPENAI_API_KEY or GROQ_API_KEY must be set for LLM fallback to work.

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


# -----------------------------------------------------------------------------
# Public data model
# -----------------------------------------------------------------------------

@dataclass
class Intent:
    kind: str                     # 'greet'|'news'|'report'|'explain'|'compare'|'trend'|'unknown'
    metric: Optional[str] = None  # 'growth_7d'|'cfr_30d_closed'|'icu_rate_30d'|'vaccinated_rate_30d'
    scope: Optional[str] = None   # 'br'|'uf'
    uf: Optional[str] = None      # 'SP','RJ',...
    confidence: float = 0.0       # 0..1 (heuristic / LLM)
    days_back: Optional[int] = None


# -----------------------------------------------------------------------------
# Normalization
# -----------------------------------------------------------------------------

def _normalize(s: str) -> str:
    """Lowercase, strip accents, collapse whitespace; keep alnum + spaces."""
    s = (s or "").lower().strip()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = re.sub(r"\s+", " ", s)
    return s


# -----------------------------------------------------------------------------
# LLM fallback (optional)
# -----------------------------------------------------------------------------

INTENT_USE_LLM = os.getenv("INTENT_USE_LLM", "0") == "1"
INTENT_MIN_CONF_FOR_RULES = 0.5  # below this we try LLM

class LLMIntent(BaseModel):
    kind: Literal["greet", "news", "report", "explain", "trend", "compare", "unknown"]
    metric: str | None = None
    scope: Literal["br", "uf"] | None = None
    uf: str | None = None
    days_back: int | None = None
    confidence: float = Field(ge=0, le=1)

_LLM_SYSTEM = """Você é um roteador de intenções para um agente de SRAG (PT-BR).
Tarefas:
- Classifique a mensagem do usuário em: greet | news | report | explain | trend | compare | unknown.
- Se for follow-up (ex.: "e no RJ?"), use o contexto dado (previous_intent) ao decidir.
- Extraia UF (sigla) se houver e defina scope=uf/br.
- Extraia métrica (growth_7d, cfr_30d_closed, icu_rate_30d, vaccinated_rate_30d) quando fizer sentido.
- days_back: 1 (hoje), 7, 30, 90 se o texto sugerir; senão null.
Responda APENAS JSON válido com estes campos: kind, metric, scope, uf, days_back, confidence.
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

    # Strict JSON validation
    try:
        data = LLMIntent.model_validate_json(raw).model_dump()
    except ValidationError:
        # Best-effort: maybe it's raw JSON string w/o quotes issues
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


# -----------------------------------------------------------------------------
# UF detection (name -> code, or uppercase sigla)
# -----------------------------------------------------------------------------

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
    # 1) Two-letter uppercase sigla
    m = re.search(r"\b([A-Z]{2})\b", orig_text or "")
    if m and m.group(1) in _UF_CODES:
        return "uf", m.group(1)

    # 2) Full name (normalized)
    t = _normalize(orig_text)
    for name, code in _UF_BY_NAME.items():
        if re.search(rf"\b{name}\b", t):
            return "uf", code

    return "br", None


# -----------------------------------------------------------------------------
# Metric synonyms -> canonical ids
# -----------------------------------------------------------------------------

_METRIC_ALIASES: Dict[str, str] = {
    # growth
    "taxa de aumento": "growth_7d",
    "crescimento 7d": "growth_7d",
    "aumento 7 dias": "growth_7d",
    "growth": "growth_7d",
    # cfr
    "cfr": "cfr_30d_closed",
    "crf": "cfr_30d_closed",
    "case fatality rate": "cfr_30d_closed",
    "taxa de letalidade": "cfr_30d_closed",
    "letalidade": "cfr_30d_closed",
    "taxa de mortalidade de casos": "cfr_30d_closed",
    # icu
    "uti": "icu_rate_30d",
    "taxa de uti": "icu_rate_30d",
    "icu rate": "icu_rate_30d",
    "percentual de casos com uti": "icu_rate_30d",
    "internacao em uti": "icu_rate_30d",
    "admissao em uti": "icu_rate_30d",
    # vaccinated
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


# -----------------------------------------------------------------------------
# days_back parser
# -----------------------------------------------------------------------------

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


# -----------------------------------------------------------------------------
# Rule-based scoring
# -----------------------------------------------------------------------------

_RULES: Dict[str, List[str]] = {
    "greet": [
        r"\b(oi|ola|ol[aá])\b", r"\b(bom dia|boa tarde|boa noite)\b",
        r"\b(eai|e a[ií])\b", r"\b(alo|al[oó])\b",
        r"\b(tudo bem|tudo bom)\b",
        r"\b(quem (e|é) voc[eê]|o que voc[eê] faz|como voc[eê] funciona)\b",
        r"\b(ajuda|help)\b",
    ],
    "news": [
        r"\bnoticia[s]?\b", r"\bultimas? noticia[s]?\b", r"\bnovidade[s]?\b",
        r"\batualiza(c|ç)(a|o|ões|oes)\b", r"\bnews\b", r"\bcontexto\b",
        r"\b(o que saiu|que saiu)\b", r"\btem novidades?\b",
    ],
    "report": [
        r"\brelat[oó]rio(s)?\b", r"\brelat[oó]rio padr[aã]o\b", r"\breport\b",
        r"\bsum[aá]rio\b", r"\bresumo\b", r"\ban[aá]lise\b", r"\bger(ar|e)\b",
    ],
    "explain": [
        r"\bexplicar\b", r"\bexplica\b", r"\bo que (e|é|eh)\b",
        r"\bdefini(c|ç)[aã]o\b", r"\b(gloss[aá]rio|glossary)\b",
        r"\bsignifica\b", r"\bmeaning\b",
    ],
    "compare": [
        r"\bcompar(ar|e)\b", r"\branking\b", r"\b(maiores|menores|piores|melhores|top)\b",
    ],
    "trend": [
        r"\btend[eê]ncia[s]?\b", r"\bevolu[cç][aã]o\b",
        r"\b[uú]ltimos? (7|30|12) (dias|mes(es)?)\b", r"\bcurva\b",
        r"\bs[eé]rie(s)? temporal(is)?\b", r"\btrend\b",
    ],
}

def _score_intents(t_norm: str) -> Dict[str, int]:
    """Return dict of intent->hits using regex rules."""
    scores: Dict[str, int] = {k: 0 for k in _RULES.keys()}
    for kind, pats in _RULES.items():
        for p in pats:
            if re.search(p, t_norm):
                scores[kind] += 1
    return scores


# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------

def classify(text: str, previous_intent: Intent | None = None) -> Intent:
    """Rule-first classification with optional LLM fallback and follow-up support."""
    orig = text or ""
    t_norm = _normalize(orig)

    # 1) Scope/UF
    scope, uf = _detect_uf_and_scope(orig)

    # 2) Rule scoring
    scores = _score_intents(t_norm)
    priority = ["greet", "news", "report", "explain", "trend", "compare"]
    top_kind, top_score = "unknown", 0
    for k in priority:
        if scores.get(k, 0) > top_score:
            top_kind, top_score = k, scores[k]
    if top_score == 0:
        top_kind = "unknown"

    metric = _detect_metric(t_norm)
    total_hits = sum(scores.values())
    conf_rules = (top_score / total_hits) if total_hits else 0.0
    days_back_hint = parse_days_back(orig)

    intent_rules = Intent(
        kind=top_kind,
        metric=metric,
        scope=scope,
        uf=uf,
        confidence=round(conf_rules, 3),
        days_back=days_back_hint,
    )

    # 3) LLM fallback if enabled or low-confidence or follow-up-like text
    looks_followup = bool(re.search(r"\b(e no|e em|e pra|e pro|e para)\b", t_norm))
    must_try_llm = INTENT_USE_LLM or conf_rules < INTENT_MIN_CONF_FOR_RULES or looks_followup

    if must_try_llm:
        intent_llm = _llm_classify(orig, previous_intent)
        if intent_llm.kind != "unknown" and intent_llm.confidence >= conf_rules:
            return intent_llm

    return intent_rules


def extract_explain_term(text: str) -> str:
    """Extract term after 'explicar/explica/o que e/é/eh'; fallback: last clause."""
    t = (text or "").strip()
    t_norm = _normalize(t)
    for trigger in ("explicar", "explica", "o que e", "o que eh", "o que é"):
        if t_norm.startswith(trigger):
            cand = t[len(trigger):].strip(" :?.,;")
            return cand if cand else t
    tokens = re.split(r"[?.,;:]", t.strip())
    return (tokens[-1] or t).strip()


# -----------------------------------------------------------------------------
# Small helpers used by the UI
# -----------------------------------------------------------------------------

def greet_message() -> str:
    """Short self-introduction for greet intent (Markdown)."""
    return (
        "Olá! 👋 Eu sou o agente SRAG. Posso:\n"
        "- 📰 Trazer **notícias recentes** (com links) — ex.: *“tem novidades de SRAG em Pernambuco?”*\n"
        "- 📊 Gerar o **relatório padrão** (Brasil ou por **UF**)\n"
        "- 📖 **Explicar** métricas/termos — ex.: *“o que é CFR?”*\n"
        "- 📈 Comentar **tendências** (7d/30d/12m)\n\n"
        "Como posso ajudar agora?"
    )


# -----------------------------------------------------------------------------
# Unified handler for the UI (returns reply + resolved intent)
# -----------------------------------------------------------------------------

def handle(user_text: str, previous_intent: Intent | None = None) -> tuple[str, Intent]:
    """
    Unified entrypoint used by the UI (Streamlit/CLI).
    Returns:
        (markdown_reply, resolved_intent)

    Behavior:
      - Classifies the text (rule-first, optional LLM fallback via `classify`).
      - Routes to the corresponding feature.
      - Always returns a Markdown string; never raises on expected failures.
    """
    # Classify (supports follow-ups via previous_intent)
    it = classify(user_text, previous_intent=previous_intent)

    # 1) Greetings / self-intro
    if it.kind == "greet":
        return greet_message(), it

    # 2) News (Tavily-backed)
    if it.kind == "news":
        try:
            # Local import to avoid circular deps at import time
            from .news_client import fetch_recent_news_srag, summarize_news_items
            extra = f"Brasil {it.uf}" if it.uf else "Brasil"
            items = fetch_recent_news_srag(
                limit=8,
                days_back=it.days_back or 14,
                query=extra,
            )
            if not items:
                return (
                    "Não encontrei **notícias recentes** de SRAG com os filtros atuais "
                    "(tente ampliar para **30 dias** ou remover o filtro de UF).",
                    it,
                )
            return summarize_news_items(items, max_items=8), it
        except Exception as exc:
            return (
                f"Falha ao buscar notícias: `{exc}`\n\n"
                "Verifique se a variável de ambiente **TAVILY_API_KEY** está configurada "
                "e se há conectividade de rede.",
                it,
            )

    # 3) Explain (glossary-driven; no LLM required)
    if it.kind == "explain":
        try:
            from .tools import glossary_lookup
            term = extract_explain_term(user_text)
            explanation = glossary_lookup(term)
            return f"**{term}** — {explanation}", it
        except Exception as exc:
            return f"Não consegui explicar o termo agora: `{exc}`", it

    # 4) Report (BR or UF)
    if it.kind == "report":
        try:
            from .generator import build_report
            from .schemas import ReportInput
            scope = "uf" if it.uf else "br"
            out = build_report(ReportInput(scope=scope, uf=it.uf))
            return out.report_md, it
        except Exception as exc:
            return (
                "Não consegui gerar o relatório.\n\n"
                f"**Erro:** `{exc}`\n\n"
                "Dicas:\n"
                "- Confirme conexão com o DuckDB/dados (camadas Gold/Silver).\n"
                "- Verifique chaves do LLM (OPENAI_API_KEY/GROQ_API_KEY) se a síntese for necessária.",
                it,
            )

    # 5) Trend (quick textual insight using last-7 vs previous-7)
    if it.kind == "trend":
        try:
            from .tools import get_series
            scope = "uf" if it.uf else "br"
            series = get_series(scope=scope, uf=it.uf)
            daily = series.get("daily")
            if daily is None or len(daily) < 2:
                where = f"**{it.uf}**" if it.uf else "**Brasil**"
                return f"Sem dados suficientes para tendência em {where}.", it

            # Compute 7d vs previous 7d if possible
            if len(daily) >= 14:
                last_7 = float(daily.tail(7)["y"].sum())
                prev_7 = float(daily.tail(14).head(7)["y"].sum())
                trend_7d = None if prev_7 == 0 else 100.0 * (last_7 - prev_7) / prev_7
            else:
                trend_7d = None

            where = f"**{it.uf}**" if it.uf else "**Brasil**"
            pct = "indisponível" if trend_7d is None else f"{trend_7d:.1f}%"
            msg = (
                f"**Tendência (últimos 7 vs. 7 anteriores)** em {where}: {pct}.\n"
                f"Pontos diários disponíveis: **{len(daily)}**."
            )
            return msg, it
        except Exception as exc:
            return f"Não foi possível calcular a tendência agora: `{exc}`", it

    # 6) Compare (placeholder — keep UX honest)
    if it.kind == "compare":
        return (
            "Comparações/rankings ainda não estão plugados. "
            "Quer comparar por **casos (30d)**, **UTI%** ou **CFR**? "
            "Posso priorizar essa funcionalidade se você disser o que prefere.",
            it,
        )

    # 7) Fallback / disambiguation
    return (
        "Não entendi bem. Você quer **notícias**, **relatório**, **explicação** de algum termo, "
        "**tendências** ou **comparar** UFs?\n\n"
        "Exemplos:\n"
        "- *“tem novidades de SRAG em Pernambuco?”*\n"
        "- *“gerar relatório padrão do RJ”*\n"
        "- *“o que é CFR?”*",
        it,
    )



# -----------------------------------------------------------------------------
# Manual test
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    samples = [
        "oi, tudo bem? o que você faz?",
        "quero as últimas notícias de SRAG no Brasil",
        "tem novidades de SRAG em Pernambuco hoje?",
        "e no RJ?",
        "gerar relatório padrão do RJ",
        "me explique sobre CFR",
        "tendência nos últimos 30 dias",
        "SRAG",
    ]
    prev = None
    for s in samples:
        reply, prev = handle(s, previous_intent=prev)
        print(f"\n> {s}\n{reply}\nintent={prev}")
