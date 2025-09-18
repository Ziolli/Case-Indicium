# src/case_indicium/agent/settings.py
from __future__ import annotations

"""
Agent configuration settings.

This module centralizes runtime configuration for the SRAG agent, including:
- LLM model routing defaults (OpenAI / Groq)
- News retrieval tunables (cache, ranking, language, sources, keywords)
- Tavily search options (optional news/general web search)

All values can be overridden via environment variables. Sensible defaults are
provided to make the system run in development without extra setup.

Environment variables (selected):
  # LLM models
  - OPENAI_MODEL              (default: "gpt-4o-mini")
  - GROQ_MODEL                (default: "llama-3.3-70b-versatile")

  # News collection
  - NEWS_TTL_HOURS            (default: "6")
  - NEWS_MAX_ITEMS            (default: "8")
  - NEWS_CACHE_PATH           (default: "data/cache/news_srag.json")
  - NEWS_LANG                 (default: "pt")
  - NEWS_DAYS_BACK            (default: "30")
  - NEWS_MIN_KW_HITS         (default: "0")   # 0 = do not filter by keyword hits
  - NEWS_RANK_REC_W           (default: "2.0")
  - NEWS_RANK_KW_W            (default: "1.0")
  - NEWS_KEYWORDS             (JSON list or comma-separated)
  - NEWS_RSS_URLS             (JSON list or comma-separated)

  # Tavily (optional)
  - TAVILY_API_KEY
  - TAVILY_SEARCH_DEPTH       (default: "basic")   # "basic" | "advanced"
  - TAVILY_TOPIC              (default: "news")    # "news"  | "general"
  - TAVILY_INCLUDE_DOMAINS    (JSON list or CSV)
  - TAVILY_EXCLUDE_DOMAINS    (JSON list or CSV)
"""

import json
import os
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple


# -------------------------
# Small helpers
# -------------------------

def _json_env(name: str, default_list: Iterable[str]) -> Tuple[str, ...]:
    """
    Read a JSON list from an environment variable; if missing or invalid,
    return the provided default list as a tuple.

    Accepts both:
      - Proper JSON: '["foo","bar"]'
      - Empty/invalid values → defaults

    Args:
        name: Environment variable name.
        default_list: Fallback iterable of strings.

    Returns:
        Tuple[str, ...]: Parsed values or defaults.
    """
    try:
        raw = os.getenv(name, "")
        if not raw:
            return tuple(default_list)
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return tuple(str(x) for x in parsed)
        return tuple(default_list)
    except Exception:
        return tuple(default_list)


def _list_env(name: str, default: Iterable[str] = ()) -> List[str]:
    """
    Read a list-like environment variable from JSON or CSV.

    Priority:
      1) If value looks like JSON ('[...]'), try to parse JSON list.
      2) Otherwise, split by comma and trim.

    Args:
        name: Environment variable name.
        default: Fallback iterable of strings.

    Returns:
        List[str]: Parsed items or defaults.
    """
    value = os.getenv(name, "")
    if value.strip().startswith("["):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed if str(x).strip()]
        except Exception:
            return list(default)
    # CSV path
    items = [x.strip() for x in value.split(",") if x.strip()]
    return items or list(default)


# -------------------------
# LLM routing defaults
# -------------------------

OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")


# -------------------------
# News settings
# -------------------------

NEWS_TTL_HOURS: int = int(os.getenv("NEWS_TTL_HOURS", "6"))
NEWS_MAX_ITEMS: int = int(os.getenv("NEWS_MAX_ITEMS", "8"))
NEWS_CACHE_PATH: Path = Path(os.getenv("NEWS_CACHE_PATH", "data/cache/news_srag.json"))
NEWS_LANG: str = os.getenv("NEWS_LANG", "pt")
NEWS_DAYS_BACK: int = int(os.getenv("NEWS_DAYS_BACK", "30"))
NEWS_MIN_KW_HITS: int = int(os.getenv("NEWS_MIN_KW_HITS", "0"))  # 0 = no keyword-hit filtering
NEWS_RANK_REC_W: float = float(os.getenv("NEWS_RANK_REC_W", "2.0"))
NEWS_RANK_KW_W: float = float(os.getenv("NEWS_RANK_KW_W", "1.0"))

# Keywords and feeds support JSON or CSV
NEWS_KEYWORDS: Tuple[str, ...] = _json_env(
    "NEWS_KEYWORDS",
    ["srag", "síndrome respiratória aguda", "síndrome respiratória"],
)

NEWS_RSS_URLS: Tuple[str, ...] = _json_env(
    "NEWS_RSS_URLS",
    [
        "https://portal.fiocruz.br/noticias/rss.xml",
        "https://g1.globo.com/rss/g1/saude.xml",
        "https://noticias.uol.com.br/saude/ultimas/index.xml",
    ],
)


# -------------------------
# Tavily search (optional)
# -------------------------

TAVILY_API_KEY: str | None = os.getenv("TAVILY_API_KEY")
TAVILY_SEARCH_DEPTH: str = os.getenv("TAVILY_SEARCH_DEPTH", "basic")   # "basic" | "advanced"
TAVILY_TOPIC: str = os.getenv("TAVILY_TOPIC", "news")                   # "news"  | "general"

TAVILY_INCLUDE_DOMAINS: List[str] = _list_env("TAVILY_INCLUDE_DOMAINS", [])
TAVILY_EXCLUDE_DOMAINS: List[str] = _list_env("TAVILY_EXCLUDE_DOMAINS", [])


__all__ = [
    # LLM
    "OPENAI_MODEL",
    "GROQ_MODEL",
    # News
    "NEWS_TTL_HOURS",
    "NEWS_MAX_ITEMS",
    "NEWS_CACHE_PATH",
    "NEWS_LANG",
    "NEWS_DAYS_BACK",
    "NEWS_MIN_KW_HITS",
    "NEWS_RANK_REC_W",
    "NEWS_RANK_KW_W",
    "NEWS_KEYWORDS",
    "NEWS_RSS_URLS",
    # Tavily
    "TAVILY_API_KEY",
    "TAVILY_SEARCH_DEPTH",
    "TAVILY_TOPIC",
    "TAVILY_INCLUDE_DOMAINS",
    "TAVILY_EXCLUDE_DOMAINS",
]
