"""DB layer for OAuth: clients, codes, refresh tokens.

All four core operations a working AS needs:
1. Register a client (DCR / RFC 7591)
2. Look up a client by id (consent UI uses this)
3. Create + redeem an authorization code (single-use, PKCE-bound)
4. Issue + rotate refresh tokens

The agents table is reused — an OAuth approval mints a regular Agent that
shows up in the dashboard alongside legacy URL-key agents.
"""

from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from ..db import acquire
from .services_helpers import sha256_hex  # avoid circular import with agents

_log = logging.getLogger(__name__)

CODE_TTL_MIN = 10
REFRESH_TTL_DAYS = 30


# ---- Clients (DCR) ----


async def register_client(
    *,
    client_name: str,
    redirect_uris: list[str],
    grant_types: list[str] | None = None,
    response_types: list[str] | None = None,
    token_endpoint_auth_method: str = "none",
    logo_uri: str | None = None,
    client_uri: str | None = None,
    software_id: str | None = None,
    software_version: str | None = None,
) -> dict[str, Any]:
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO oauth_clients (
                client_name, redirect_uris, grant_types, response_types,
                token_endpoint_auth_method, logo_uri, client_uri,
                software_id, software_version
            )
            VALUES ($1, $2, COALESCE($3, ARRAY['authorization_code', 'refresh_token']),
                    COALESCE($4, ARRAY['code']), $5, $6, $7, $8, $9)
            RETURNING client_id, client_name, redirect_uris, grant_types,
                      response_types, token_endpoint_auth_method, logo_uri,
                      client_uri, software_id, software_version, created_at
            """,
            client_name,
            redirect_uris,
            grant_types,
            response_types,
            token_endpoint_auth_method,
            logo_uri,
            client_uri,
            software_id,
            software_version,
        )
    return dict(row)


async def get_client(client_id: str) -> dict[str, Any] | None:
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT client_id, client_name, redirect_uris, grant_types,
                   response_types, token_endpoint_auth_method, logo_uri,
                   client_uri, software_id, software_version, created_at
            FROM oauth_clients
            WHERE client_id = $1 AND deleted_at IS NULL
            """,
            client_id,
        )
    return dict(row) if row else None


# ---- Authorization codes ----


async def create_authorization_code(
    *,
    client_id: str,
    owner_id: str,
    agent_id: str,
    redirect_uri: str,
    code_challenge: str,
    code_challenge_method: str,
    scope: str | None,
    resource: str | None,
) -> str:
    """Insert a new auth code row, return the plaintext code (single-use)."""
    plaintext = secrets.token_hex(32)
    expires = datetime.now(UTC) + timedelta(minutes=CODE_TTL_MIN)
    async with acquire() as conn:
        await conn.execute(
            """
            INSERT INTO oauth_codes (
                code_hash, client_id, owner_id, agent_id, redirect_uri,
                code_challenge, code_challenge_method, scope, resource, expires_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """,
            sha256_hex(plaintext),
            client_id,
            owner_id,
            agent_id,
            redirect_uri,
            code_challenge,
            code_challenge_method,
            scope,
            resource,
            expires,
        )
    return plaintext


async def consume_authorization_code(plaintext: str) -> dict[str, Any] | None:
    """Atomically mark the code as used and return its bindings.

    Returns ``None`` if the code doesn't exist, was already used, or has
    expired. The mark+read happens in a single UPDATE so a concurrent reuse
    can't race past validation.
    """
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE oauth_codes
            SET used_at = now()
            WHERE code_hash = $1
              AND used_at IS NULL
              AND expires_at > now()
            RETURNING client_id, owner_id, agent_id, redirect_uri,
                      code_challenge, code_challenge_method, scope, resource
            """,
            sha256_hex(plaintext),
        )
    return dict(row) if row else None


# ---- Refresh tokens ----


async def issue_refresh_token(
    *,
    client_id: str,
    agent_id: str,
    owner_id: str,
    scope: str | None,
) -> str:
    plaintext = secrets.token_hex(32)
    expires = datetime.now(UTC) + timedelta(days=REFRESH_TTL_DAYS)
    async with acquire() as conn:
        await conn.execute(
            """
            INSERT INTO oauth_refresh_tokens (
                token_hash, client_id, agent_id, owner_id, scope, expires_at
            )
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            sha256_hex(plaintext),
            client_id,
            agent_id,
            owner_id,
            scope,
            expires,
        )
    return plaintext


async def consume_refresh_token(plaintext: str, *, client_id: str) -> dict[str, Any] | None:
    """Validate + revoke (rotate). Returns the row's bindings on success.

    Per OAuth 2.1 §4.3.1 we MUST rotate refresh tokens for public clients —
    the caller issues a new one and returns it alongside the access token.
    Reusing the old one after rotation is detectable as `revoked_at IS NOT NULL`.
    """
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE oauth_refresh_tokens
            SET revoked_at = now()
            WHERE token_hash = $1
              AND client_id = $2
              AND revoked_at IS NULL
              AND expires_at > now()
            RETURNING agent_id, owner_id, scope
            """,
            sha256_hex(plaintext),
            client_id,
        )
    return dict(row) if row else None
