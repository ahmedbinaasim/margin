"""Owner-scoped agent CRUD for the dashboard. Plaintext keys returned ONCE on mint."""

from __future__ import annotations

import secrets
from typing import Any

import bcrypt

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
            WHERE owner_id = $1
            ORDER BY created_at DESC
            """,
            owner_id,
        )
    return [dict(r) for r in rows]
