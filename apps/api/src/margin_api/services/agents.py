"""Owner-scoped agent CRUD for the dashboard. Plaintext keys returned ONCE on mint."""

from __future__ import annotations

import secrets
from typing import Any

import bcrypt

from .. import auth as auth_mod
from ..db import acquire


def mint_api_key() -> str:
    return "ag_live_" + secrets.token_hex(12)


async def create_agent_for_owner(owner_id: str, name: str) -> tuple[dict[str, Any], str]:
    plaintext = mint_api_key()
    key_prefix = plaintext[:12]
    key_hash = bcrypt.hashpw(plaintext.encode(), bcrypt.gensalt()).decode()
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO agents (owner_id, name, key_hash, key_prefix)
            VALUES ($1, $2, $3, $4)
            RETURNING agent_id, name, key_prefix, last_used_at, created_at
            """,
            owner_id,
            name,
            key_hash,
            key_prefix,
        )
    return dict(row), plaintext


async def list_agents_for_owner(owner_id: str) -> list[dict[str, Any]]:
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT agent_id, name, key_prefix, last_used_at, created_at
            FROM agents
            WHERE owner_id = $1 AND deleted_at IS NULL
            ORDER BY created_at DESC
            """,
            owner_id,
        )
    return [dict(r) for r in rows]


async def update_agent_name(
    owner_id: str, agent_id: str, new_name: str
) -> dict[str, Any] | None:
    """Rename an agent. Returns the updated row or None if not owned."""
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE agents
            SET name = $3
            WHERE agent_id = $1 AND owner_id = $2 AND deleted_at IS NULL
            RETURNING agent_id, name, key_prefix, last_used_at, created_at
            """,
            agent_id,
            owner_id,
            new_name,
        )
    return dict(row) if row else None


async def delete_agent(owner_id: str, agent_id: str) -> bool:
    """Soft-delete: marks deleted_at and invalidates the in-process auth cache
    so the revoked key stops authing immediately. Returns True if a row was
    actually deleted (i.e. owned + still active)."""
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE agents
            SET deleted_at = now()
            WHERE agent_id = $1 AND owner_id = $2 AND deleted_at IS NULL
            RETURNING key_prefix
            """,
            agent_id,
            owner_id,
        )
    if row is None:
        return False
    # Flush the auth cache for this prefix so the deleted key stops working
    # before the 60s TTL expires.
    auth_mod._AGENT_CACHE.pop(row["key_prefix"], None)
    return True
