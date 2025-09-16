#!/usr/bin/env python
"""
Minimal LLM routing smoke test.

- Uses the prompt scaffolding.
- Sends a tiny fake payload (no DB needed).
- Prints the first 800 chars of the model output.

Run:
  poetry run python scripts/test_llm.py
"""

from __future__ import annotations
from case_indicium.agent.prompt import SYSTEM_PROMPT_PT, build_user_prompt
from case_indicium.agent.llm_router import generate_text


def main():
    # Tiny fake payload (so we can test routing without DB)
    kpis = {
        "cases_7d": 120,
        "cases_prev_7d": 100,
        "growth_7d_pct": 20.0,
        "cfr_closed_30d_pct": 2.5,
        "icu_rate_30d_pct": 15.4,
        "vaccinated_rate_30d_pct": 48.2,
    }
    daily = [{"x": "2025-08-25", "y": 100}, {"x": "2025-08-26", "y": 110}]
    monthly = [{"x": "2025-08-01", "y": 3400}, {"x": "2025-09-01", "y": 3600}]
    news = [{
        "title": "SRAG shows slight increase in region X",
        "url": "https://example.org/news/1",
        "source": "Example News",
        "published_at": "2025-09-15",
        "summary": "Local authorities monitor ICU pressure."
    }]

    user = build_user_prompt(
        scope="br",
        uf=None,
        as_of_day="2025-09-07",
        kpis=kpis,
        daily_series_30d=daily,
        monthly_series_12m=monthly,
        news=news,
        notes=[
            "ICU rate is % of cases with ICU admission (not bed occupancy).",
            "Vaccinated rate is % among notified cases (not population coverage)."
        ],
    )

    text = generate_text(user, SYSTEM_PROMPT_PT, temperature=0.2, max_tokens=800)
    print(text[:800])


if __name__ == "__main__":
    main()
