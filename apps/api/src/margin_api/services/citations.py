"""Citation fetch + extract + R2 archive.

Pipeline (SPEC §4.1 / §9):
1. httpx GET (15 s timeout, follow redirects)
2. trafilatura.extract → cleaned markdown
3. sha256(normalize(markdown)) → page_hash
4. R2 PUT raw HTML at pages/<page_hash>.html (best-effort)
5. INSERT citation row

On any fetch/extract/upload failure we still INSERT a row with fetch_status=0
so the trail isn't lost.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx

from .. import storage
from ..db import acquire
from . import events as events_svc


_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "mc_cid", "mc_eid",
}


def _normalize_url(url: str) -> str:
    """Lowercase host, drop fragment, strip tracking params."""
    p = urlparse(url)
    host = p.hostname.lower() if p.hostname else ""
    netloc = host
    if p.port and not (
        (p.scheme == "http" and p.port == 80) or (p.scheme == "https" and p.port == 443)
    ):
        netloc = f"{host}:{p.port}"
    if "@" in p.netloc:
        netloc = p.netloc.split("@", 1)[0] + "@" + netloc

    if p.query:
        kept = []
        for piece in p.query.split("&"):
            if not piece:
                continue
            k = piece.split("=", 1)[0]
            if k.lower() in _TRACKING_PARAMS:
                continue
            kept.append(piece)
        query = "&".join(kept)
    else:
        query = ""
    return urlunparse((p.scheme.lower(), netloc, p.path or "", "", query, ""))


def _normalize_markdown(md: str) -> str:
    return re.sub(r"\s+", " ", md or "").strip().lower()


def _page_hash(md: str) -> str:
    return hashlib.sha256(_normalize_markdown(md).encode("utf-8")).hexdigest()


async def cite(
    *,
    agent_id: str,
    finding_id: str,
    url: str,
    excerpt: str,
) -> dict[str, Any]:
    """Idempotent on (finding_id, page_hash). Always inserts a row even on fetch failure."""

    canonical = _normalize_url(url)

    fetched_at: datetime | None = None
    fetch_status = 0
    raw_html: bytes = b""
    md_text = ""
    page_hash = ""

    try:
        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            headers={"User-Agent": "Margin/0.1 (+https://margin.dev)"},
        ) as client:
            resp = await client.get(url)
        fetch_status = resp.status_code
        fetched_at = datetime.now(timezone.utc)
        raw_html = resp.content
        if 200 <= resp.status_code < 300 and raw_html:
            try:
                import trafilatura

                md = trafilatura.extract(
                    raw_html.decode(resp.encoding or "utf-8", errors="replace"),
                    output_format="markdown",
                    with_metadata=True,
                    favor_precision=True,
                )
                md_text = md or ""
            except Exception:
                md_text = ""
    except Exception:
        # Network error, DNS fail, timeout. Record the row anyway.
        fetch_status = 0
        fetched_at = datetime.now(timezone.utc)

    if md_text:
        page_hash = _page_hash(md_text)
    else:
        # Use the canonical URL itself for the dedup key when we have no body.
        page_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    r2_key: str | None = None
    if raw_html and storage.is_enabled():
        try:
            r2_key = f"pages/{page_hash}.html"
            await storage.put_html(r2_key, raw_html)
        except Exception:
            r2_key = None

    # Idempotent insert.
    async with acquire() as conn:
        existing = await conn.fetchrow(
            "SELECT * FROM citations WHERE finding_id = $1 AND page_hash = $2",
            finding_id,
            page_hash,
        )
        if existing is not None:
            row = existing
        else:
            row = await conn.fetchrow(
                """
                INSERT INTO citations
                    (finding_id, url, canonical_url, excerpt, page_hash,
                     r2_key, fetched_at, fetch_status)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING *
                """,
                finding_id,
                url,
                canonical,
                excerpt,
                page_hash,
                r2_key,
                fetched_at,
                fetch_status,
            )

        # Project_id (for event scoping) lives on the finding.
        proj = await conn.fetchrow(
            "SELECT project_id FROM findings WHERE finding_id = $1",
            finding_id,
        )
        project_id = proj["project_id"] if proj else None
        await events_svc.emit(
            conn,
            agent_id=agent_id,
            project_id=project_id,
            kind="cite",
            payload={
                "finding_id": finding_id,
                "citation_id": row["citation_id"],
                "url": canonical[:160],
                "fetch_status": fetch_status,
            },
        )

    archive_url = None
    if row["r2_key"] and storage.is_enabled():
        try:
            archive_url = await storage.signed_get(row["r2_key"], ttl=604800)
        except Exception:
            archive_url = None

    return {
        "citation_id": row["citation_id"],
        "finding_id": row["finding_id"],
        "page_hash": row["page_hash"],
        "fetched_at": row["fetched_at"],
        "fetch_status": row["fetch_status"],
        "archive_url": archive_url,
    }


async def list_for_finding(finding_id: str) -> list[dict[str, Any]]:
    async with acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM citations WHERE finding_id = $1 ORDER BY created_at ASC",
            finding_id,
        )
    return [dict(r) for r in rows]
