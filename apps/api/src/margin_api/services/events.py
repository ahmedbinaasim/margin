"""Append-only event log + Postgres LISTEN/NOTIFY fanout for the dashboard.

Writers call :func:`emit`. Subscribers (the SSE route) call :func:`subscribe`,
which opens a dedicated connection, runs ``LISTEN events``, and yields each
notification filtered to a given agent.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import asyncpg

from ..config import get_settings


async def emit(
    conn: asyncpg.Connection,
    *,
    agent_id: str,
    project_id: str | None,
    kind: str,
    payload: dict[str, Any],
) -> int:
    """Append an event row + pg_notify fanout. Payload should be small (<500 chars)."""
    event_id = await conn.fetchval(
        """
        INSERT INTO events (agent_id, project_id, kind, payload)
        VALUES ($1, $2, $3, $4::jsonb)
        RETURNING event_id
        """,
        agent_id,
        project_id,
        kind,
        json.dumps(payload),
    )
    notify_payload = json.dumps(
        {
            "event_id": event_id,
            "agent_id": agent_id,
            "project_id": project_id,
            "kind": kind,
            "payload": payload,
        }
    )
    # pg_notify payload size limit is 8000 bytes; keep payloads small.
    await conn.execute("SELECT pg_notify('events', $1)", notify_payload)
    return event_id


async def subscribe(
    agent_id: str,
    since: int | None = None,
    queue_size: int = 128,
) -> AsyncIterator[dict[str, Any]]:
    """Yield events for one agent. Replays everything after ``since`` first, then live."""

    settings = get_settings()
    conn: asyncpg.Connection = await asyncpg.connect(settings.database_url)
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=queue_size)
    loop = asyncio.get_running_loop()

    def _on_notify(_conn, _pid, _channel, payload: str) -> None:
        try:
            obj = json.loads(payload)
        except Exception:
            return
        if obj.get("agent_id") != agent_id:
            return
        # Use call_soon_threadsafe even though asyncpg is async; keeps things simple.
        try:
            queue.put_nowait(obj)
        except asyncio.QueueFull:
            # Drop oldest to keep the stream fresh.
            try:
                queue.get_nowait()
            except Exception:
                pass
            try:
                queue.put_nowait(obj)
            except Exception:
                pass

    try:
        await conn.add_listener("events", _on_notify)

        # Replay any history strictly after ``since``.
        if since is not None:
            rows = await conn.fetch(
                """
                SELECT event_id, agent_id, project_id, kind, payload
                FROM events
                WHERE agent_id = $1 AND event_id > $2
                ORDER BY event_id ASC
                LIMIT 200
                """,
                agent_id,
                since,
            )
            for r in rows:
                payload = r["payload"]
                if isinstance(payload, str):
                    payload = json.loads(payload)
                yield {
                    "event_id": r["event_id"],
                    "agent_id": r["agent_id"],
                    "project_id": r["project_id"],
                    "kind": r["kind"],
                    "payload": payload,
                }

        # Live forever (the route lifecycle ends iteration).
        while True:
            obj = await queue.get()
            yield obj
    finally:
        try:
            await conn.remove_listener("events", _on_notify)
        except Exception:
            pass
        await conn.close()
        # silence unused var warning
        _ = loop


async def list_recent(agent_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """For a polling fallback / initial paint."""
    from ..db import acquire

    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT event_id, agent_id, project_id, kind, payload, created_at
            FROM events
            WHERE agent_id = $1
            ORDER BY event_id DESC
            LIMIT $2
            """,
            agent_id,
            limit,
        )
    out: list[dict[str, Any]] = []
    for r in rows:
        payload = r["payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        out.append(
            {
                "event_id": r["event_id"],
                "agent_id": r["agent_id"],
                "project_id": r["project_id"],
                "kind": r["kind"],
                "payload": payload,
                "created_at": r["created_at"].isoformat(),
            }
        )
    return out
