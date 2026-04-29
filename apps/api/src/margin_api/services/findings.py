"""Finding CRUD with content-hash dedup and pgvector embedding."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

import asyncpg

from .. import embeddings
from ..db import acquire
from . import events as events_svc
from . import projects as projects_svc


def _content_hash(claim: str, evidence: str) -> str:
    norm = (claim.strip() + "\x00" + evidence.strip()).lower()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def _vec_to_pgvector(v: list[float]) -> str:
    """Format a list of floats as a pgvector literal."""
    return "[" + ",".join(f"{x:.7f}" for x in v) + "]"


async def add_finding(
    *,
    agent_id: str,
    project_id: str,
    claim: str,
    evidence: str,
    source: str | None,
    confidence: float,
    contradicts: str | None,
) -> dict[str, Any]:
    """Idempotent: same (project_id, content_hash) returns the existing row."""

    if contradicts:
        # Validate contradicts belongs to the same project (FK alone doesn't enforce that).
        async with acquire() as conn:
            row = await conn.fetchrow(
                "SELECT project_id FROM findings WHERE finding_id = $1",
                contradicts,
            )
            if row is None or row["project_id"] != project_id:
                raise ValueError("contradicts must reference a finding in the same project")

    chash = _content_hash(claim, evidence)

    async with acquire() as conn:
        existing = await conn.fetchrow(
            """
            SELECT finding_id, project_id, created_at
            FROM findings
            WHERE project_id = $1 AND content_hash = $2
            """,
            project_id,
            chash,
        )
        if existing is not None:
            return {
                "finding_id": existing["finding_id"],
                "project_id": existing["project_id"],
                "created_at": existing["created_at"],
                "deduped": True,
            }

    # Embed once (lifts up out of the connection scope so we don't hold it).
    vec = (await embeddings.embed([f"{claim} {evidence}"], input_type="document"))[0]

    async with acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                INSERT INTO findings
                    (project_id, agent_id, claim, evidence, source_url,
                     confidence, contradicts, embedding, content_hash)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8::vector, $9)
                ON CONFLICT (project_id, content_hash) DO NOTHING
                RETURNING finding_id, project_id, created_at
                """,
                project_id,
                agent_id,
                claim,
                evidence,
                source,
                confidence,
                contradicts,
                _vec_to_pgvector(vec),
                chash,
            )
            if row is None:
                # Lost a race; fetch the row that won.
                existing = await conn.fetchrow(
                    "SELECT finding_id, project_id, created_at FROM findings WHERE project_id = $1 AND content_hash = $2",
                    project_id,
                    chash,
                )
                if existing is None:
                    raise RuntimeError("dedup race: row vanished")
                return {
                    "finding_id": existing["finding_id"],
                    "project_id": existing["project_id"],
                    "created_at": existing["created_at"],
                    "deduped": True,
                }

            await projects_svc.touch(project_id, conn=conn)
            await events_svc.emit(
                conn,
                agent_id=agent_id,
                project_id=project_id,
                kind="add_finding",
                payload={
                    "finding_id": row["finding_id"],
                    "claim": claim[:120],
                    "confidence": confidence,
                },
            )

    return {
        "finding_id": row["finding_id"],
        "project_id": row["project_id"],
        "created_at": row["created_at"],
        "deduped": False,
    }


async def query_findings(
    *,
    project_id: str,
    semantic_query: str,
    limit: int = 10,
    min_confidence: float = 0.0,
) -> list[dict[str, Any]]:
    """Cosine semantic search over findings in one project."""

    qvec = (await embeddings.embed([semantic_query], input_type="query"))[0]
    qvec_lit = _vec_to_pgvector(qvec)

    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                finding_id, claim, evidence, source_url, confidence,
                1 - (embedding <=> $1::vector) AS similarity
            FROM findings
            WHERE project_id = $2 AND confidence >= $3 AND embedding IS NOT NULL
            ORDER BY embedding <=> $1::vector
            LIMIT $4
            """,
            qvec_lit,
            project_id,
            min_confidence,
            limit,
        )

    out: list[dict[str, Any]] = []
    for r in rows:
        evidence = r["evidence"] or ""
        excerpt = evidence if len(evidence) <= 280 else evidence[:280] + "..."
        out.append(
            {
                "finding_id": r["finding_id"],
                "claim": r["claim"],
                "evidence_excerpt": excerpt,
                "source_url": r["source_url"],
                "confidence": float(r["confidence"]),
                "similarity": float(r["similarity"] or 0.0),
            }
        )
    return out


async def list_findings(project_id: str) -> list[dict[str, Any]]:
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT finding_id, project_id, claim, evidence, source_url,
                   confidence, contradicts, created_at
            FROM findings
            WHERE project_id = $1
            ORDER BY created_at ASC
            """,
            project_id,
        )
    return [dict(r) for r in rows]


async def get_finding(finding_id: str) -> dict[str, Any] | None:
    async with acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM findings WHERE finding_id = $1",
            finding_id,
        )
    return dict(row) if row else None
