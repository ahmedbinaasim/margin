"""Human review request lifecycle."""

from __future__ import annotations

from typing import Any

from ..db import acquire
from . import events as events_svc
from . import projects as projects_svc


async def request_review(*, agent_id: str, project_id: str, reason: str) -> dict[str, Any]:
    async with acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                INSERT INTO reviews (project_id, reason)
                VALUES ($1, $2)
                RETURNING review_id, project_id, reason, status, created_at
                """,
                project_id,
                reason,
            )
            await projects_svc.update_status(project_id, "review_requested", conn=conn)
            await events_svc.emit(
                conn,
                agent_id=agent_id,
                project_id=project_id,
                kind="request_human_review",
                payload={"review_id": row["review_id"], "reason": reason[:200]},
            )
    return dict(row)


async def list_for_project(project_id: str) -> list[dict[str, Any]]:
    async with acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM reviews WHERE project_id = $1 ORDER BY created_at DESC",
            project_id,
        )
    return [dict(r) for r in rows]


async def decide(
    review_id: str, decision: str, note: str | None
) -> dict[str, Any] | None:
    """Approve or reject a pending review. Used by dashboard."""
    if decision not in ("approved", "rejected"):
        raise ValueError("decision must be 'approved' or 'rejected'")
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE reviews
            SET status = $1, decided_note = $2, decided_at = now()
            WHERE review_id = $3 AND status = 'pending'
            RETURNING *
            """,
            decision,
            note,
            review_id,
        )
        if row is not None:
            # Bring the project back to active on approval.
            new_status = "active" if decision == "approved" else "active"
            await projects_svc.update_status(row["project_id"], new_status, conn=conn)
    return dict(row) if row else None
