"""Project CRUD + branching."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import asyncpg

from ..db import acquire
from . import events as events_svc


async def create_project(
    agent_id: str,
    topic: str,
    depth: str,
    deadline: datetime | None,
) -> dict[str, Any]:
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO projects (agent_id, topic, depth, deadline)
            VALUES ($1, $2, $3, $4)
            RETURNING project_id, topic, depth, deadline, status, created_at, parent_id
            """,
            agent_id,
            topic,
            depth,
            deadline,
        )
        await events_svc.emit(
            conn,
            agent_id=agent_id,
            project_id=row["project_id"],
            kind="start_research",
            payload={"topic": topic[:160], "depth": depth},
        )
    return dict(row)


async def get_project(project_id: str, agent_id: str | None = None) -> dict[str, Any] | None:
    """Fetch a project; optionally enforce agent ownership."""
    async with acquire() as conn:
        if agent_id is not None:
            row = await conn.fetchrow(
                "SELECT * FROM projects WHERE project_id = $1 AND agent_id = $2",
                project_id,
                agent_id,
            )
        else:
            row = await conn.fetchrow(
                "SELECT * FROM projects WHERE project_id = $1",
                project_id,
            )
    return dict(row) if row else None


async def list_projects_for_agent(
    agent_id: str, limit: int = 20, status: str | None = None
) -> list[dict[str, Any]]:
    async with acquire() as conn:
        if status:
            rows = await conn.fetch(
                """
                SELECT p.project_id, p.topic, p.depth, p.status, p.parent_id,
                       p.updated_at, p.created_at,
                       (SELECT COUNT(*) FROM findings f WHERE f.project_id = p.project_id) AS num_findings
                FROM projects p
                WHERE p.agent_id = $1 AND p.status = $2
                ORDER BY p.updated_at DESC
                LIMIT $3
                """,
                agent_id,
                status,
                limit,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT p.project_id, p.topic, p.depth, p.status, p.parent_id,
                       p.updated_at, p.created_at,
                       (SELECT COUNT(*) FROM findings f WHERE f.project_id = p.project_id) AS num_findings
                FROM projects p
                WHERE p.agent_id = $1
                ORDER BY p.updated_at DESC
                LIMIT $2
                """,
                agent_id,
                limit,
            )
    return [dict(r) for r in rows]


async def branch_project(
    parent_project_id: str, agent_id: str, reason: str
) -> dict[str, Any]:
    """Create a child project. Inherits topic + depth from parent."""
    async with acquire() as conn:
        parent = await conn.fetchrow(
            "SELECT * FROM projects WHERE project_id = $1 AND agent_id = $2",
            parent_project_id,
            agent_id,
        )
        if parent is None:
            raise ValueError(f"project {parent_project_id} not found for this agent")

        row = await conn.fetchrow(
            """
            INSERT INTO projects (agent_id, topic, depth, deadline, parent_id, branch_reason)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING project_id, topic, depth, deadline, status, parent_id,
                      branch_reason, created_at
            """,
            agent_id,
            parent["topic"],
            parent["depth"],
            parent["deadline"],
            parent_project_id,
            reason,
        )
        await events_svc.emit(
            conn,
            agent_id=agent_id,
            project_id=row["project_id"],
            kind="branch_project",
            payload={"parent_id": parent_project_id, "reason": reason[:200]},
        )
    return dict(row)


async def update_status(
    project_id: str, status: str, conn: asyncpg.Connection | None = None
) -> None:
    sql = "UPDATE projects SET status = $1, updated_at = now() WHERE project_id = $2"
    if conn is None:
        async with acquire() as c:
            await c.execute(sql, status, project_id)
    else:
        await conn.execute(sql, status, project_id)


async def touch(project_id: str, conn: asyncpg.Connection | None = None) -> None:
    sql = "UPDATE projects SET updated_at = now() WHERE project_id = $1"
    if conn is None:
        async with acquire() as c:
            await c.execute(sql, project_id)
    else:
        await conn.execute(sql, project_id)
