"""JWT access tokens for the MCP transport.

Self-contained tokens — no DB lookup on the hot path. We sign with the same
HS256 secret used for owner JWTs, but distinguish them by ``aud`` (this token
is bound to ``{api_base_url}/mcp``) and ``token_type=access``. The owner JWT
issued by Firebase sign-in has ``scope=owner`` and a different audience, so
the two paths can't accidentally cross-authenticate.

Validation: signature, ``iss``, ``aud``, ``exp``, ``token_type``. Returns the
decoded claims on success or ``None`` on any failure.
"""

from __future__ import annotations

import logging
import secrets
import time
from typing import TypedDict

import jwt

from ..config import get_settings

_log = logging.getLogger(__name__)

ACCESS_TOKEN_TTL_SECONDS = 3600  # 1h


class AccessTokenClaims(TypedDict):
    iss: str
    sub: str  # agent_id
    aud: str
    iat: int
    exp: int
    scope: str
    owner_id: str
    client_id: str
    token_type: str
    jti: str


def mcp_audience() -> str:
    """The canonical MCP resource URI — what tokens are bound to."""
    return f"{get_settings().api_base_url}/mcp"


def issue_access_token(
    *,
    agent_id: str,
    owner_id: str,
    client_id: str,
    scope: str = "mcp",
) -> tuple[str, int]:
    """Mint a JWT access token. Returns ``(jwt, expires_in_seconds)``."""
    settings = get_settings()
    now = int(time.time())
    payload: AccessTokenClaims = {
        "iss": settings.api_base_url,
        "sub": agent_id,
        "aud": mcp_audience(),
        "iat": now,
        "exp": now + ACCESS_TOKEN_TTL_SECONDS,
        "scope": scope,
        "owner_id": owner_id,
        "client_id": client_id,
        "token_type": "access",
        "jti": secrets.token_hex(8),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    return token, ACCESS_TOKEN_TTL_SECONDS


def verify_access_token(token: str) -> AccessTokenClaims | None:
    """Decode + validate. Returns claims or ``None`` (logging the reason)."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            audience=mcp_audience(),
            issuer=settings.api_base_url,
            options={"require": ["exp", "iat", "sub", "aud", "iss"]},
        )
    except jwt.PyJWTError as e:
        _log.info("oauth_access_token_invalid err=%r", e)
        return None
    if payload.get("token_type") != "access":
        _log.info("oauth_access_token_wrong_type type=%r", payload.get("token_type"))
        return None
    return payload  # type: ignore[return-value]
