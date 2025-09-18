# src/case_indicium/agent/intent_router.py
"""
Lightweight PT-first intent router for the SRAG agent.

Goals
-----
- Keep it rule-based but resilient: normalization, synonyms, UF detection.
- Distinguish clearly among: greet | news | report | explain | trend | compare | unknown.
- Provide scope ('br'|'uf'), UF code when present, metric id, confidence score.
- Include helpers to extract "explain" term and a days_back window from natural text.

Notes
-----
- This module does not call the LLM. It only classifies text and extracts hints.
- Regex lists are short on purpose; you can extend them without changing code flow.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict, Tuple, List
import re
import unicodedata


@dataclass
class Intent:
    kind: str  # 'greet'|'news'|'report'|'explain'|'compare'|'trend'|'unknown'
    metric: Optional[str] = None            # e.g., 'growth_7d'|'cfr_30d_closed'|'icu_rate_30d'|'vaccinated_rate_30d'
    scope: Optional[str] = None             # 'br'|'uf'
    uf: Optional[str] = None                # 'SP','RJ',...
    confidence: float = 0.0                 # 0..1 (heuristic)
    days_back: Optional[int] = None         # parsed window hint (e.g., 1, 7, 30)


# ---------------------------------------------------------------------------
# Normalization utilities
# ---------------------------------------------------------------------------

def _normalize(s: str) -> str:
    """Lowercase, strip accents, collapse whitespace; keep alnum + basic punctuation."""
    s = (s or "").lower().strip()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")  # remove accents
    s = re.sub(r"\s+", " ", s)
    return s


# ---------------------------------------------------------------------------
# UF detection (name -> code, plus uppercase sigla)
# ---------------------------------------------------------------------------

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
    """
    Return ('uf'|'br', UF_CODE|None) by scanning original text for:
      1) two-letter uppercase siglas (SP, RJ, ...), or
      2) full UF names (normalized).
    """
    # 1) two uppercase letters as a whole word
    m = re.search(r"\b([A-Z]{2})\b", orig_text or "")
    if m and m.group(1) in _UF_CODES:
        return "uf", m.group(1)

    # 2) full name
    t = _normalize(orig_text)
    for name, code in _UF_BY_NAME.items():
        if re.search(rf"\b{name}\b", t):
            return "uf", code

    return "br", None


# ---------------------------------------------------------------------------
# Metric synonyms -> canonical ids (align with metrics_registry.py)
# ---------------------------------------------------------------------------

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
    """Try phrase-first mapping; fallback token check for 'cfr'/'crf'."""
    for k, mid in sorted(_METRIC_ALIASES.items(), key=lambda x: -len(x[0])):
        if k in t_norm:
            return mid
    tokens = t_norm.split()
    if "cfr" in tokens or "crf" in tokens:
        return "cfr_30d_closed"
    return None


# ---------------------------------------------------------------------------
# Days-back window parsing (today / week / month)
# ---------------------------------------------------------------------------

def parse_days_back(text: str) -> int:
    """
    Extract a sensible days_back window from natural PT text.
    Defaults to 14 if nothing is found.
    """
    t = _normalize(text)
    if any(k in t for k in ("hoje", "agora")):
        return 1
    if any(k in t for k in ("ontem",)):
        return 2
    if re.search(r"\b(7|sete)\b.*\bdias\b", t) or "semana" in t:
        return 7
    if re.search(r"\b(30|trinta)\b.*\bdias\b", t) or any(k in t for k in ("mes", "mês")):
        return 30
    if re.search(r"\b(90|noventa)\b.*\bdias\b", t) or "trimestre" in t:
        return 90
    return 14


# ---------------------------------------------------------------------------
# Intent rules (regex scoring)
# ---------------------------------------------------------------------------

_RULES: Dict[str, List[str]] = {
    # greet goes first to short-circuit “hello” style messages
    "greet": [
        r"\b(oi|ola|ol[aá])\b",
        r"\b(bom dia|boa tarde|boa noite)\b",
        r"\b(eai|e a[ií])\b",
        r"\b(alo|al[oó])\b",
        r"\b(tudo bem|tudo bom)\b",
        r"\b(quem (e|é) voc[eê]\b|o que voc[eê] faz\b|como voc[eê] funciona\b)",
        r"\b(ajuda|help)\b",
    ],
    "news": [
        r"\bnoticia[s]?\b",
        r"\bultimas? noticia[s]?\b",
        r"\bnovidade[s]?\b",
        r"\b(atualiza(c|ç)(a|o|ões|oes))\b",
        r"\bnews\b",
        r"\bcontexto\b",
        r"\b(o que saiu|que saiu)\b",
        r"\btem novidades?\b",
    ],
    "report": [
        r"\brelat[oó]rio(s)?\b",
        r"\brelat[oó]rio padr[aã]o\b",
        r"\breport\b",
        r"\bsum[aá]rio\b",
        r"\bresumo\b",
        r"\ban[aá]lise\b",
        r"\bger(ar|e)\b",
    ],
    "explain": [
        r"\bexplicar\b",
        r"\bexplica\b",
        r"\bo que (e|é|eh)\b",
        r"\bdefini(c|ç)[aã]o\b",
        r"\b(gloss[aá]rio|glossary)\b",
        r"\bsignifica\b",
        r"\bmeaning\b",
    ],
    "compare": [
        r"\bcompar(ar|e)\b",
        r"\branking\b",
        r"\b(maiores|menores|piores|melhores|top)\b",
    ],
    "trend": [
        r"\btend[eê]ncia[s]?\b",
        r"\bevolu[cç][aã]o\b",
        r"\b[uú]ltimos? (7|30|12) (dias|mes(es)?)\b",
        r"\bcurva\b",
        r"\bs[eé]rie(s)? temporal(is)?\b",
        r"\btrend\b",
    ],
}


def _score_intents(t_norm: str) -> Dict[str, int]:
    """Return a dict of intent -> hits count based on regex rules."""
    scores: Dict[str, int] = {k: 0 for k in _RULES.keys()}
    for kind, pats in _RULES.items():
        for p in pats:
            if re.search(p, t_norm):
                scores[kind] += 1
    return scores


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def classify(text: str) -> Intent:
    """
    Classify a user message in PT-BR into a high-level intent.

    Returns:
        Intent(kind, metric, scope, uf, confidence, days_back)
    """
    orig = text or ""
    t_norm = _normalize(orig)

    # 1) scope + UF
    scope, uf = _detect_uf_and_scope(orig)

    # 2) scores
    scores = _score_intents(t_norm)

    # 3) tie-breaker order: greet > news > report > explain > trend > compare > unknown
    priority = ["greet", "news", "report", "explain", "trend", "compare"]
    top_kind = "unknown"
    top_score = 0
    for k in priority:
        if scores.get(k, 0) > top_score:
            top_kind, top_score = k, scores[k]
    if top_score == 0:
        top_kind = "unknown"

    # 4) metric (optional)
    metric = _detect_metric(t_norm)

    # 5) confidence (simple heuristic)
    total_hits = sum(scores.values())
    confidence = (top_score / total_hits) if total_hits else 0.0

    # 6) days_back hint (used mainly by news/trend)
    window = parse_days_back(orig)

    return Intent(
        kind=top_kind,
        metric=metric,
        scope=scope,
        uf=uf,
        confidence=round(confidence, 3),
        days_back=window,
    )


def extract_explain_term(text: str) -> str:
    """
    Extract term after 'explicar/explica/o que e/é/eh'.
    Fallback: return the last clause without trailing punctuation.
    """
    t = (text or "").strip()
    t_norm = _normalize(t)
    for trigger in ("explicar", "explica", "o que e", "o que eh", "o que é"):
        if t_norm.startswith(trigger):
            cand = t[len(trigger):].strip(" :?.,;")
            return cand if cand else t
    # fallback: last 'phrase' without terminal punctuation
    tokens = re.split(r"[?.,;:]", t.strip())
    return (tokens[-1] or t).strip()


# ---------------------------------------------------------------------------
# Optional: tiny handler for greet (string you can print directly)
# ---------------------------------------------------------------------------

def greet_message() -> str:
    """
    Short self-introduction for greet intent.
    Keep it UI-friendly (Markdown).
    """
    return (
        "Olá! 👋 Eu sou o agente SRAG. Posso:\n"
        "- 📰 Trazer **notícias recentes** (com links) — ex.: *“tem novidades de SRAG em Pernambuco?”*\n"
        "- 📊 Gerar o **relatório padrão** (BR ou por **UF**)\n"
        "- 📖 **Explicar** métricas/termos — ex.: *“o que é CFR?”*\n"
        "- 📈 Comentar **tendências** (7d/30d/12m)\n\n"
        "Como posso ajudar agora?"
    )

# --- cole a partir daqui no final do intent_router.py ------------------------

def handle(user_text: str) -> str:
    """
    Single entrypoint used by the UI (Streamlit/CLI).
    Routes the user text to the right feature and returns Markdown.
    """
    it = classify(user_text)

    # 1) Saudação / apresentação
    if it.kind == "greet":
        return greet_message()

    # 2) Notícias
    if it.kind == "news":
        # imports locais para evitar dependências cíclicas
        from .news_client import fetch_recent_news_srag, summarize_news_items

        extra = f"Brasil {it.uf}" if it.uf else "Brasil"
        items = fetch_recent_news_srag(
            limit=8, days_back=it.days_back or 14, query=extra
        )
        if not items:
            return "Não encontrei notícias recentes de SRAG com esses filtros. Tente '30 dias'."
        return summarize_news_items(items, max_items=8)

    # 3) Explicar termos/métricas
    if it.kind == "explain":
        from .tools import glossary_lookup
        term = extract_explain_term(user_text)
        return glossary_lookup(term)

    # 4) Relatório padrão (BR ou UF)
    if it.kind == "report":
        from .generator import build_report
        from .schemas import ReportInput
        scope = "uf" if it.uf else "br"
        out = build_report(ReportInput(scope=scope, uf=it.uf))
        return out.report_md  # markdown pronto

    # 5) Tendências (texto curto usando as séries já existentes)
    if it.kind == "trend":
        from .tools import get_series
        scope = "uf" if it.uf else "br"
        series = get_series(scope=scope, uf=it.uf)
        daily = series["daily"]
        # 7d vs 7 anteriores (só pra dar um insight rápido)
        if len(daily) >= 14:
            last_7 = daily.tail(7)["y"].sum()
            prev_7 = daily.tail(14).head(7)["y"].sum()
            trend_7d = None if prev_7 == 0 else 100.0 * (last_7 - prev_7) / prev_7
        else:
            trend_7d = None
        where = f"**{it.uf}**" if it.uf else "**Brasil**"
        msg = f"**Tendência (últimos 7 vs. 7 anteriores)** em {where}: "
        msg += f"{trend_7d:.1f}%." if trend_7d is not None else "indisponível."
        msg += f"\nPontos diários: {len(daily)}."
        return msg

    # 6) Comparações / ranking (placeholder)
    if it.kind == "compare":
        return ("Comparações/rankings ainda não estão plugados. "
                "Quer comparar por **casos (30d)**, **UTI%** ou **CFR**?")

    # 7) Fallback
    return ("Não entendi bem. Você quer **notícias**, **relatório**, "
            "**explicação** de algum termo, **tendências** ou **comparar** UFs?")


# ---------------------------------------------------------------------------
# Quick manual test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    samples = [
        "oi, tudo bem? o que você faz?",
        "quero as últimas notícias de SRAG no Brasil",
        "tem novidades de SRAG em Pernambuco hoje?",
        "gerar relatório padrão do RJ",
        "explicar taxa de letalidade",
        "comparar ranking por UTI",
        "tendência nos últimos 30 dias",
        "SRAG",
    ]
    for s in samples:
        it = classify(s)
        print(f"- {s!r}\n  -> {it}")
