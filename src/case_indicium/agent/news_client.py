# src/case_indicium/agent/news_client.py
"""
Minimal SRAG news fetcher + summarizer using tavily-python (Brazil-focused).

This module provides two functions:
  1) fetch_recent_news_srag(...)  -> List[NewsItem]
  2) summarize_news_items(...)    -> Markdown (PT-BR) with inline citations and sources

Design goals
------------
- Keep it simple and predictable.
- Use Tavily's official SDK for search.
- Summaries are generated in Brazilian Portuguese. If the LLM call fails,
  a deterministic bullet list fallback is returned.

Environment variables
---------------------
- TAVILY_API_KEY : Required. Tavily API key for tavily-python.
- (Optional) OPENAI_API_KEY / GROQ_API_KEY for the LLM (via llm_router).
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import List, Optional, Sequence

from tavily import TavilyClient

from .schemas import NewsItem


# ---------------------------------------------------------------------------
# Small utilities
# ---------------------------------------------------------------------------

def _time_range(days_back: int) -> str:
    """Map a day window to Tavily's 'time_range' enum."""
    if days_back <= 1:
        return "day"
    if days_back <= 7:
        return "week"
    if days_back <= 30:
        return "month"
    return "year"


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

def fetch_recent_news_srag(
    limit: int = 8,
    query: Optional[str] = None,
    *,
    days_back: int = 7,
) -> List[NewsItem]:
    """
    Fetch recent SRAG-related articles via Tavily (Brazil-focused).

    Args:
        limit: Maximum number of items to return (default 8).
        query: Optional extra filter appended to the base query.
        days_back: Window mapped to Tavily's time_range ('day'|'week'|'month'|'year').

    Returns:
        List[NewsItem] (possibly empty).
    """
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY is not set.")

    base = "Novidades sobre SRAG no Brasil"
    if query:
        base = f"{base} {query}"

    client = TavilyClient(api_key)
    resp = client.search(
        query=base,
        time_range=_time_range(days_back),
        country="brazil",
        topic="general",
        search_depth="basic",
        max_results=max(1, int(limit)),
        include_answer=False,
    )

    items: List[NewsItem] = []
    for r in (resp or {}).get("results", []):
        title = (r.get("title") or "").strip() or "(sem título)"
        url = (r.get("url") or "").strip()
        if not url:
            continue
        # prefer provider 'source' if present, else netloc
        source = (r.get("source") or "").strip()
        if not source:
            try:
                source = url.split("/")[2]
            except Exception:
                source = "desconhecido"
        published = (
            r.get("published_date")
            or r.get("published_time")
            or r.get("date")
            or _now_utc_iso()
        )
        summary = (r.get("content") or r.get("snippet") or "").strip() or None

        items.append(
            NewsItem(
                title=title,
                url=url,
                source=source,
                published_at=str(published),
                summary=summary,
            )
        )

    return items[:limit]


# ---------------------------------------------------------------------------
# Summarize
# ---------------------------------------------------------------------------

def summarize_news_items(
    items: Sequence[NewsItem],
    *,
    max_items: int = 8,
    audience: str = "gestores de saúde",
    temperature: float = 0.2,
    max_tokens: int = 900,
) -> str:
    """
    Summarize a small list of NewsItem into PT-BR markdown with citations.

    Output rules:
      - Write in Brazilian Portuguese, clear and concise.
      - Up to ~6 bullet points; add a brief context sentence if useful.
      - Use inline numeric citations [n] that correspond to the item id (1-based).
      - End with a "Fontes" section mapping [n] -> markdown link.

    If the LLM call fails, returns a deterministic fallback summary.

    Args:
        items: Iterable of NewsItem to summarize.
        max_items: Max items to include in the prompt.
        audience: Optional audience hint for tone.
        temperature: LLM temperature (passed to llm_router).
        max_tokens: LLM max tokens (passed to llm_router).

    Returns:
        Markdown string.
    """
    sel = list(items)[:max_items]
    if not sel:
        return "Não encontrei notícias relevantes no período selecionado."

    # Build compact payload for the model
    rows = []
    for i, it in enumerate(sel, 1):
        rows.append(
            {
                "id": i,
                "title": it.title,
                "source": it.source,
                "published_at": it.published_at,
                "summary": (it.summary or "")[:400],
            }
        )

    system_pt = (
        "Você é um analista epidemiológico. Escreva em português do Brasil, claro e objetivo. "
        "Resuma as notícias sem inventar informações. "
        "Use citações numéricas entre colchetes [n] que correspondem ao id do item."
    )
    user_pt = (
        "Resuma as principais novidades de SRAG para {audience}. "
        "Use no máximo 6 bullets e, se fizer sentido, uma frase inicial de contexto. "
        "Mantenha números e datas existentes. "
        "Itens (cada um tem um id para citação):\n"
        "{rows}\n\n"
        "Regras:\n"
        "- Não invente dados que não estejam nos itens.\n"
        "- Sempre use citações [n] para cada afirmação derivada de um item.\n"
        "- Foque em implicações para vigilância/assistência (tendências, alertas, campanhas, leitos etc.)."
    ).format(audience=audience, rows=rows)

    # Try LLM; if it fails, return a deterministic fallback
    try:
        from .llm_router import generate_text  # local import to avoid circular deps

        body = generate_text(
            user_content=user_pt,
            system_content=system_pt,
            temperature=temperature,
            max_tokens=max_tokens,
        ).strip()
    except Exception:
        # Fallback: simple bullet list using titles only
        bullets = "\n".join(f"- [{i}] {it.title}" for i, it in enumerate(sel, 1))
        body = (
            "### Principais pontos (resumo simples)\n"
            f"{bullets}\n\n"
            "_Obs.: resumo simplificado porque o serviço de LLM não estava disponível._"
        )

    # Append sources with links
    fontes_lines = []
    for i, it in enumerate(sel, 1):
        date_str = (it.published_at or "")[:10]
        fontes_lines.append(f"[{i}] {it.title} — *{it.source}, {date_str}*. {it.url}")

    return body + "\n\n**Fontes**\n" + "\n".join(f"- {line}" for line in fontes_lines)


__all__ = ["fetch_recent_news_srag", "summarize_news_items"]


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        data = fetch_recent_news_srag(limit=5, days_back=7)
        md = summarize_news_items(data, max_items=5)
        print(md)
    except Exception as exc:
        print("Error:", exc)
