"""API-key auth (bcrypt) for both REST and MCP, plus dashboard JWT.

REST: ``Authorization: Bearer <key>``.
MCP:  the key is in the URL path (``/mcp/<key>``) — Claude.ai's connector UI
does not let users set headers (SPEC §9).

Dashboard: short-lived JWTs minted by the magic-link flow identify owners,
not agents. Owners use the dashboard to mint and list agent keys.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Annotated

import bcrypt
import jwt
from fastapi import Depends, Header, HTTPException, Request, status

from .config import get_settings
from .db import acquire


@dataclass
class Agent:
    agent_id: str
    owner_id: str
    name: str
    key_prefix: str


@dataclass
class Owner:
    owner_id: str
    email: str


# In-process cache: prefix -> (agent_id, owner_id, name, key_prefix, key_hash, cached_at).
# Bcrypt is intentionally slow; we cache verifications for 60s.
_AGENT_CACHE: dict[str, tuple[Agent, str, float]] = {}
_AGENT_CACHE_TTL = 60.0


def _key_prefix(key: str) -> str:
    return key[:12]


async def _resolve_key(plaintext: str) -> Agent:
    """Return the Agent for a plaintext key, or raise 401."""
    if not plaintext or not plaintext.startswith("ag_"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid key")

    prefix = _key_prefix(plaintext)
    now = time.monotonic()

    cached = _AGENT_CACHE.get(prefix)
    if cached:
        agent, key_hash, cached_at = cached
        if now - cached_at < _AGENT_CACHE_TTL:
            if bcrypt.checkpw(plaintext.encode(), key_hash.encode()):
                return agent

    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT agent_id, owner_id, name, key_prefix, key_hash
            FROM agents
            WHERE key_prefix = $1
            """,
            prefix,
        )

    for row in rows:
        if bcrypt.checkpw(plaintext.encode(), row["key_hash"].encode()):
            agent = Agent(
                agent_id=row["agent_id"],
                owner_id=row["owner_id"],
                name=row["name"],
                key_prefix=row["key_prefix"],
            )
            _AGENT_CACHE[prefix] = (agent, row["key_hash"], now)
            # Best-effort last-used update; don't await blocking (fire and forget OK).
            try:
                await conn.execute(
                    "UPDATE agents SET last_used_at = now() WHERE agent_id = $1",
                    agent.agent_id,
                )
            except Exception:
                pass
            return agent

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid key")


async def get_agent_from_bearer(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> Agent:
    """FastAPI dependency for REST endpoints."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer")
    token = authorization.split(" ", 1)[1].strip()
    return await _resolve_key(token)


async def get_agent_from_path(api_key: str) -> Agent:
    """Used by the MCP route. The key is the ``{api_key}`` path segment."""
    return await _resolve_key(api_key)


# --- Dashboard JWT (owner-scoped) ---

def hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def issue_owner_token(owner_id: str, email: str) -> str:
    settings = get_settings()
    now = int(time.time())
    payload = {
        "sub": owner_id,
        "email": email,
        "iat": now,
        "exp": now + 60 * 60 * 24 * 7,  # 7d
        "scope": "owner",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_owner_token(token: str) -> Owner:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"bad token: {e}")
    if payload.get("scope") != "owner":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="bad scope")
    return Owner(owner_id=payload["sub"], email=payload["email"])


async def get_owner_from_bearer(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> Owner:
    """Dashboard endpoints depend on this for owner identity."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer")
    token = authorization.split(" ", 1)[1].strip()
    return decode_owner_token(token)


def clear_cache() -> None:
    """For tests — reset the bcrypt verification cache."""
    _AGENT_CACHE.clear()


# Common Depends type aliases to keep route signatures terse.
AgentDep = Annotated[Agent, Depends(get_agent_from_bearer)]
OwnerDep = Annotated[Owner, Depends(get_owner_from_bearer)]


def get_request_agent(req: Request) -> Agent:
    """For paths that handled auth manually (e.g. MCP middleware sets it)."""
    agent = getattr(req.state, "agent", None)
    if not isinstance(agent, Agent):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    return agent
