"""Magic-link sign-in: 6-digit code, 10-minute TTL, single-use."""

from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

from ..auth import hash_code
from ..config import get_settings
from ..db import acquire
from ..email_templates import magic_link_html, magic_link_text

CODE_TTL_MIN = 10

_log = logging.getLogger(__name__)


async def _send_magic_link(email: str, code: str) -> bool:
    """Send the magic-link via SMTP. Returns True on success.

    Provider-agnostic: any SMTP server works (Resend, Brevo, SMTP2GO, Gmail, etc.)
    by setting SMTP_HOST/PORT/USERNAME/PASSWORD env vars. If SMTP_HOST or
    SMTP_PASSWORD is unset, returns False — the caller surfaces the code in
    the API response (dev escape hatch).
    """
    settings = get_settings()
    if not (settings.smtp_host and settings.smtp_password):
        return False

    try:
        import aiosmtplib

        msg = EmailMessage()
        msg["From"] = settings.smtp_from
        msg["To"] = email
        msg["Subject"] = f"Your Margin sign-in code: {code}"
        msg.set_content(magic_link_text(code, CODE_TTL_MIN))
        msg.add_alternative(magic_link_html(code, CODE_TTL_MIN), subtype="html")

        # aiosmtplib forbids passing both use_tls and start_tls=True. Pick one.
        kwargs: dict[str, object] = {
            "hostname": settings.smtp_host,
            "port": settings.smtp_port,
            "username": settings.smtp_username,
            "password": settings.smtp_password,
            "timeout": settings.smtp_timeout,
        }
        if settings.smtp_start_tls:
            kwargs["start_tls"] = True
        elif settings.smtp_use_tls:
            kwargs["use_tls"] = True

        await aiosmtplib.send(msg, **kwargs)
        return True
    except Exception as e:
        _log.warning("smtp_send_failed email=%s err=%r", email, e)
        return False


def _new_code() -> str:
    # 6-digit numeric code (10**6 space; rate-limit + single-use protects it).
    return f"{secrets.randbelow(1_000_000):06d}"


async def request_code(email: str) -> tuple[str, bool]:
    """Issue a code. Returns (code, sent_via_email). The code itself is only
    persisted hashed; the plaintext is returned so the caller can email it
    or surface it in the dev-mode response.
    """
    code = _new_code()
    expires = datetime.now(UTC) + timedelta(minutes=CODE_TTL_MIN)

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

    sent = await _send_magic_link(email, code)
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
            if row["expires_at"] < datetime.now(UTC):
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
