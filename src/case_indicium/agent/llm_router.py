"""
LLM routing with OpenAI priority and Groq fallback.

Environment variables:
- OPENAI_API_KEY (preferred)
- OPENAI_MODEL (optional, default: gpt-4o-mini)
- GROQ_API_KEY (fallback)
- GROQ_MODEL (optional, default: llama-3.3-70b-versatile)
"""

from __future__ import annotations
import os
from typing import Tuple

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass



def _get_openai_model() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def _get_groq_model() -> str:
    return os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")


def _call_openai(messages, temperature: float = 0.2, max_tokens: int | None = None) -> str:
    # Requires openai>=1.x
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    resp = client.chat.completions.create(
        model=_get_openai_model(),
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return (resp.choices[0].message.content or "").strip()


def _call_groq(messages, temperature: float = 0.2, max_tokens: int | None = None) -> str:
    import groq
    client = groq.Groq(api_key=os.getenv("GROQ_API_KEY"))
    resp = client.chat.completions.create(
        model=_get_groq_model(),
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return (resp.choices[0].message.content or "").strip()


def pick_provider() -> Tuple[str, str]:
    """
    Returns ("openai"|"groq", model_name). Prioritizes OpenAI if key is present.
    """
    if os.getenv("OPENAI_API_KEY"):
        return "openai", _get_openai_model()
    if os.getenv("GROQ_API_KEY"):
        return "groq", _get_groq_model()
    raise RuntimeError("No LLM key configured (set OPENAI_API_KEY or GROQ_API_KEY).")


def generate_text(
    user_content: str,
    system_content: str,
    *,
    temperature: float = 0.2,
    max_tokens: int | None = None,
) -> str:
    """
    Try OpenAI first; on failure, fallback to Groq (if key available).
    """
    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]

    # Preferred provider
    if os.getenv("OPENAI_API_KEY"):
        try:
            return _call_openai(messages, temperature=temperature, max_tokens=max_tokens)
        except Exception as err_oa:
            # Fallback to Groq if possible
            if os.getenv("GROQ_API_KEY"):
                try:
                    return _call_groq(messages, temperature=temperature, max_tokens=max_tokens)
                except Exception as err_gq:
                    raise RuntimeError(
                        f"Both providers failed. OpenAI error: {err_oa}; Groq error: {err_gq}"
                    ) from err_gq
            # No fallback available
            raise RuntimeError(f"OpenAI failed and no GROQ_API_KEY set: {err_oa}") from err_oa

    # If OpenAI not configured, use Groq directly
    if os.getenv("GROQ_API_KEY"):
        try:
            return _call_groq(messages, temperature=temperature, max_tokens=max_tokens)
        except Exception as err_gq:
            raise RuntimeError(f"Groq failed: {err_gq}") from err_gq

    raise RuntimeError("No LLM key configured (set OPENAI_API_KEY or GROQ_API_KEY).")
