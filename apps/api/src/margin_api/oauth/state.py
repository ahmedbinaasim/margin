"""Signed state blob for the /oauth/authorize → dashboard handoff.

When /oauth/authorize validates an incoming request, it 302s the user's
browser to the dashboard's consent UI. The dashboard later POSTs back the
same params to /v1/oauth/authorize-decision and we re-issue an auth code.
Between those two hops the params live in a URL — so we sign them with the
JWT secret, base64url-encode the JWT, and let the dashboard pass it back
opaquely. The backend re-validates the signature + TTL on the way in.

This is just a JWT under the hood with a distinct ``token_type`` so it can
never be mistaken for an access or owner token.
"""

from __future__ import annotations

import logging
import time
from typing import TypedDict

import jwt

from ..config import get_settings

_log = logging.getLogger(__name__)

AUTH_REQUEST_TTL_SECONDS = 600  # 10 min — same as auth code TTL


class AuthRequestBlob(TypedDict):
    client_id: str
    redirect_uri: str
    code_challenge: str
    code_challenge_method: str
    state: str | None
    scope: str | None
    resource: str
    iat: int
    exp: int
    token_type: str


def sign_auth_request(
    *,
    client_id: str,
    redirect_uri: str,
    code_challenge: str,
    code_challenge_method: str,
    state: str | None,
    scope: str | None,
    resource: str,
) -> str:
    settings = get_settings()
    now = int(time.time())
    payload: AuthRequestBlob = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method,
        "state": state,
        "scope": scope,
        "resource": resource,
        "iat": now,
        "exp": now + AUTH_REQUEST_TTL_SECONDS,
        "token_type": "auth_request",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def verify_auth_request(blob: str) -> AuthRequestBlob | None:
    settings = get_settings()
    try:
        payload = jwt.decode(
            blob,
            settings.jwt_secret,
            algorithms=["HS256"],
            options={"require": ["exp", "iat"]},
        )
    except jwt.PyJWTError as e:
        _log.info("oauth_auth_request_invalid err=%r", e)
        return None
    if payload.get("token_type") != "auth_request":
        return None
    return payload  # type: ignore[return-value]
