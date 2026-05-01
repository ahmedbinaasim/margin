"""Firebase ID-token verification for the dashboard auth flow.

The frontend uses ``firebase/auth`` with Google as the only provider, gets an
ID token via ``user.getIdToken()``, and posts it here. We verify the token
with the Admin SDK, extract the user's email + display name, and let the
caller upsert an owner / issue our existing owner JWT.

Init is lazy and one-shot — the Admin SDK throws if you call
``initialize_app`` twice. Three env vars are needed (FIREBASE_PROJECT_ID,
FIREBASE_CLIENT_EMAIL, FIREBASE_PRIVATE_KEY); the private key carries
literal ``\\n`` sequences (the format inside the service-account JSON), which
we expand back to real newlines so the PEM parser is happy.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException, status

from .config import get_settings

_log = logging.getLogger(__name__)
_initialized = False


def _ensure_initialized() -> None:
    """Initialize firebase-admin once. Raises RuntimeError if env not set."""
    global _initialized
    if _initialized:
        return

    settings = get_settings()
    if not settings.firebase_enabled:
        raise RuntimeError(
            "Firebase env vars not configured (FIREBASE_PROJECT_ID, "
            "FIREBASE_CLIENT_EMAIL, FIREBASE_PRIVATE_KEY)"
        )

    import firebase_admin
    from firebase_admin import credentials

    cred = credentials.Certificate(
        {
            "type": "service_account",
            "project_id": settings.firebase_project_id,
            "client_email": settings.firebase_client_email,
            # The env var stores literal \n; PEM parser needs real newlines.
            "private_key": settings.firebase_private_key.replace("\\n", "\n"),
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    )
    firebase_admin.initialize_app(cred)
    _initialized = True


def verify_google_id_token(id_token: str) -> dict[str, Any]:
    """Verify a Firebase ID token and return its decoded claims.

    Returns a dict containing at least ``email`` and ``email_verified``;
    typically also ``name``, ``picture``, ``uid``. Raises HTTP 401 on any
    verification failure or if the email isn't verified (Google always sets
    ``email_verified=True`` for valid Google accounts, so this is mostly a
    defense against spoofed tokens that somehow slip through).
    """
    _ensure_initialized()

    from firebase_admin import auth as fb_auth

    try:
        decoded: dict[str, Any] = fb_auth.verify_id_token(id_token, check_revoked=False)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"firebase token invalid: {e}",
        ) from e

    email = decoded.get("email")
    if not email or not decoded.get("email_verified"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="email not verified",
        )
    return decoded
