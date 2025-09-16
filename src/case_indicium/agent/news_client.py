from __future__ import annotations
from datetime import datetime, timedelta, timezone
from pathlib import Path
import os, json, time
from typing import List
from .schemas import NewsItem

CACHE_PATH = Path("data/cache/news_srag.json")
CACHE_TTL_HOURS = int(os.getenv("NEWS_TTL_HOURS", "6"))

def _load_cache() -> dict | None:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None

def _save_cache(payload: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

def fetch_recent_news_srag(limit: int = 5) -> List[NewsItem]:
    """
    Minimal placeholder: reads cache or returns empty.
    Real impl: call a provider (NewsAPI/RSS/Bing) and normalize to NewsItem.
    """
    now = time.time()
    cache = _load_cache()
    if cache and now - cache.get("ts", 0) < CACHE_TTL_HOURS * 3600:
        return [NewsItem(**x) for x in cache.get("items", [])][:limit]

    # TODO: implement provider. For now, empty.
    items: List[NewsItem] = []
    _save_cache({"ts": now, "items": [x.dict() for x in items]})
    return items[:limit]
