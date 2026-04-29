"""Magic-link sign-in: 6-digit code, 10-minute TTL, single-use."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from ..auth import hash_code
from ..config import get_settings
from ..db import acquire


CODE_TTL_MIN = 10


def _new_code() -> str:
    # 6-digit numeric code (10**6 space; rate-limit + single-use protects it).
    return f"{secrets.randbelow(1_000_000):06d}"


async def request_code(email: str) -> tuple[str, bool]:
    """Issue a code. Returns (code, sent_via_email). The code itself is only
    persisted hashed; the plaintext is returned so the caller can email it
    or surface it in the dev-mode response.
    """
    settings = get_settings()
    code = _new_code()
    expires = datetime.now(timezone.utc) + timedelta(minutes=CODE_TTL_MIN)

    async with acquire() as conn:
        # Upsert owner so the email always exists.
        await conn.execute(
            """
            INSERT INTO owners (email) VALUES ($1)
            ON CONFLICT (email) DO NOTHING
            """,
            email,
        )
        await conn.execute(
            """
            INSERT INTO auth_codes (code_hash, email, expires_at)
            VALUES ($1, $2, $3)
            ON CONFLICT (code_hash) DO NOTHING
            """,
            hash_code(code),
            email,
            expires,
        )

    sent = False
    if settings.resend_api_key:
        try:
            import resend

            resend.api_key = settings.resend_api_key
            resend.Emails.send(
                {
                    "from": "Margin <noreply@margin.dev>",
                    "to": [email],
                    "subject": f"Your Margin sign-in code: {code}",
                    "text": (
                        f"Your sign-in code is: {code}\n\n"
                        f"It expires in {CODE_TTL_MIN} minutes."
                    ),
                }
            )
            sent = True
        except Exception:
            sent = False

    return code, sent


async def verify_code(email: str, code: str) -> str | None:
    """Return owner_id on success, None on failure. Single-use."""
    async with acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                SELECT code_hash, email, expires_at, used_at
                FROM auth_codes
                WHERE code_hash = $1 AND email = $2
                """,
                hash_code(code),
                email,
            )
            if row is None:
                return None
            if row["used_at"] is not None:
                return None
            if row["expires_at"] < datetime.now(timezone.utc):
                return None

            await conn.execute(
                "UPDATE auth_codes SET used_at = now() WHERE code_hash = $1",
                row["code_hash"],
            )
            owner_id = await conn.fetchval(
                "SELECT owner_id FROM owners WHERE email = $1",
                email,
            )
    return owner_id
