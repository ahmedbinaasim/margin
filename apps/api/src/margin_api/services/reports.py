"""Report rendering + publication.

Phase 3 ships the naive renderer (group by confidence buckets). Phase 6
adds the optional Groq TOC and signed R2 citation URLs (here, since both
are simple bolt-ons that don't restructure the function).
"""

from __future__ import annotations

import json
from typing import Any

from .. import llm, storage
from ..config import get_settings
from ..db import acquire
from . import events as events_svc
from . import projects as projects_svc


CONFIRMED_THRESHOLD = 0.7


async def publish_report(
    *, agent_id: str, project_id: str, fmt: str = "markdown"
) -> dict[str, Any]:
    """Render a report from this project's findings + citations and persist it."""

    async with acquire() as conn:
        project = await conn.fetchrow(
            "SELECT * FROM projects WHERE project_id = $1",
            project_id,
        )
        if project is None:
            raise ValueError(f"project {project_id} not found")
        findings = await conn.fetch(
            """
            SELECT finding_id, claim, evidence, source_url, confidence, created_at
            FROM findings
            WHERE project_id = $1
            ORDER BY created_at ASC
            """,
            project_id,
        )

        # Pre-fetch citations once per finding.
        cite_rows = await conn.fetch(
            """
            SELECT c.finding_id, c.canonical_url, c.r2_key, c.fetch_status
            FROM citations c
            JOIN findings f ON f.finding_id = c.finding_id
            WHERE f.project_id = $1
            """,
            project_id,
        )
    citations_by_finding: dict[str, list[dict[str, Any]]] = {}
    for r in cite_rows:
        citations_by_finding.setdefault(r["finding_id"], []).append(dict(r))

    if fmt == "json":
        body = json.dumps(
            {
                "topic": project["topic"],
                "depth": project["depth"],
                "findings": [
                    {
                        "claim": f["claim"],
                        "evidence": f["evidence"],
                        "source": f["source_url"],
                        "confidence": float(f["confidence"]),
                    }
                    for f in findings
                ],
            },
            indent=2,
        )
    else:
        body = await _render_markdown(
            topic=project["topic"],
            depth=project["depth"],
            findings=findings,
            citations_by_finding=citations_by_finding,
        )

    public_slug = project_id  # SPEC says default to project_id

    async with acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                INSERT INTO reports (project_id, format, body, public_slug)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (public_slug) DO UPDATE
                  SET body = EXCLUDED.body, format = EXCLUDED.format, created_at = now()
                RETURNING report_id, project_id, format, body, public_slug, created_at
                """,
                project_id,
                fmt,
                body,
                public_slug,
            )
            await projects_svc.update_status(project_id, "published", conn=conn)
            await events_svc.emit(
                conn,
                agent_id=agent_id,
                project_id=project_id,
                kind="publish_report",
                payload={
                    "report_id": row["report_id"],
                    "public_slug": public_slug,
                    "format": fmt,
                },
            )

    settings = get_settings()
    report_url = f"{settings.public_base_url}/r/{public_slug}"
    return {
        "report_id": row["report_id"],
        "project_id": row["project_id"],
        "format": row["format"],
        "public_slug": row["public_slug"],
        "report_url": report_url,
        "created_at": row["created_at"],
    }


async def _render_markdown(
    *,
    topic: str,
    depth: str,
    findings: list[Any],
    citations_by_finding: dict[str, list[dict[str, Any]]],
) -> str:
    confirmed = [f for f in findings if (f["confidence"] or 0) >= CONFIRMED_THRESHOLD]
    tentative = [f for f in findings if (f["confidence"] or 0) < CONFIRMED_THRESHOLD]

    # Optional Groq TOC.
    intro = await llm.report_toc(topic, [f["claim"] for f in confirmed])

    parts: list[str] = [f"# {topic}\n"]
    parts.append(f"_Depth: **{depth}**. {len(findings)} findings — {len(confirmed)} confirmed, {len(tentative)} tentative._\n")

    if intro:
        parts.append(intro.strip() + "\n")

    if confirmed:
        parts.append("## Confirmed (confidence ≥ 0.7)\n")
        for f in confirmed:
            parts.append(await _render_finding(f, citations_by_finding))
    if tentative:
        parts.append("## Tentative (confidence < 0.7)\n")
        for f in tentative:
            parts.append(await _render_finding(f, citations_by_finding))

    parts.append("\n---\n_Generated by [Margin](https://margin.dev)._\n")
    return "\n".join(parts)


async def _render_finding(
    f: Any, citations_by_finding: dict[str, list[dict[str, Any]]]
) -> str:
    cites = citations_by_finding.get(f["finding_id"], [])
    cite_lines: list[str] = []
    for c in cites:
        url = c.get("canonical_url") or "#"
        archive_link = ""
        if c.get("r2_key") and storage.is_enabled():
            try:
                signed = await storage.signed_get(c["r2_key"], ttl=604800)
                archive_link = f" · [archive]({signed})"
            except Exception:
                archive_link = ""
        cite_lines.append(f"[source]({url}){archive_link}")
    if f["source_url"] and not cite_lines:
        cite_lines.append(f"[source]({f['source_url']})")

    return (
        f"### {f['claim']}\n\n"
        f"> {f['evidence']}\n\n"
        f"_Confidence: {float(f['confidence']):.2f}_"
        + ("" if not cite_lines else " · " + " · ".join(cite_lines))
        + "\n"
    )


async def get_report_by_slug(slug: str) -> dict[str, Any] | None:
    async with acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM reports WHERE public_slug = $1",
            slug,
        )
    return dict(row) if row else None
