"""Groq LLM client for the report TOC. Returns ``None`` on any failure.

Per revised SPEC §7: Groq is the only LLM. There is no Gemini fallback —
if Groq errors, ``publish_report`` falls back to the naive markdown grouping.
"""

from __future__ import annotations

from collections.abc import Sequence

from .config import get_settings

_client = None


def _get_client():
    global _client
    if _client is None:
        from groq import AsyncGroq

        settings = get_settings()
        if not settings.groq_api_key:
            raise RuntimeError("groq_api_key not configured")
        _client = AsyncGroq(api_key=settings.groq_api_key)
    return _client


_TOC_SYSTEM = (
    "You write clear, terse research-report intros. "
    "Output strict markdown only — no preamble, no explanation, no code fences. "
    "Format: a 2-paragraph intro under a single H2 heading 'Overview', then a markdown TOC "
    "as a bullet list. Reference the actual claims in the bullets."
)


async def report_toc(topic: str, confirmed_bullets: Sequence[str]) -> str | None:
    """Return a markdown intro+TOC for a report, or ``None`` on any failure."""

    settings = get_settings()
    if not settings.groq_api_key or not confirmed_bullets:
        return None

    user = (
        f"Topic: {topic}\n\n"
        "Confirmed findings:\n"
        + "\n".join(f"- {b}" for b in confirmed_bullets[:30])
    )

    try:
        client = _get_client()
        resp = await client.chat.completions.create(
            model=settings.groq_model,
            temperature=0.2,
            max_tokens=400,
            messages=[
                {"role": "system", "content": _TOC_SYSTEM},
                {"role": "user", "content": user},
            ],
        )
        content = resp.choices[0].message.content
        return content.strip() if content else None
    except Exception:
        return None
