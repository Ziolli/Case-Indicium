# src/case_indicium/agent/intent_router.py
"""Very small rule-based intent router for the chat agent (PT-first)."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

@dataclass
class Intent:
    kind: str  # 'report'|'explain'|'compare'|'trend'|'news'|'unknown'
    metric: Optional[str] = None
    scope: Optional[str] = None  # 'br'|'uf'
    uf: Optional[str] = None

KEYWORDS_REPORT = ("gerar relatório", "relatório padrão", "report", "sumário")
KEYWORDS_EXPLAIN = ("explicar", "o que é", "definição", "glossário", "glossary", "meaning")
KEYWORDS_COMPARE = ("comparar", "ranking", "top", "maiores", "piores", "melhores")
KEYWORDS_TREND = ("tendência", "evolução", "últimos 30 dias", "últimos 12 meses", "trend")
KEYWORDS_NEWS = ("notícia", "noticias", "news", "atualizações", "contexto")

def classify(text: str) -> Intent:
    t = (text or "").lower()
    if any(k in t for k in KEYWORDS_REPORT):
        return Intent(kind="report")
    if any(k in t for k in KEYWORDS_EXPLAIN):
        return Intent(kind="explain")
    if any(k in t for k in KEYWORDS_COMPARE):
        return Intent(kind="compare")
    if any(k in t for k in KEYWORDS_TREND):
        return Intent(kind="trend")
    if any(k in t for k in KEYWORDS_NEWS):
        return Intent(kind="news")
    return Intent(kind="unknown")

def extract_explain_term(text: str) -> str:
    """Try to extract the term after 'explicar ...' or return last token."""
    t = (text or "").strip().lower()
    for trigger in ("explicar", "explica", "o que e", "o que é"):
        if t.startswith(trigger):
            cand = t[len(trigger):].strip(" :?.,;")
            if cand:
                return cand
    # fallback: last word
    return t.strip(" ?.,;").split()[-1]
