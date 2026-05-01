"""Owner upsert + first-login welcome email.

Owners are identified by email (unique). The dashboard auth flow upserts the
row, and on the FIRST login (welcomed_at IS NULL) we schedule a non-blocking
welcome email via FastAPI's BackgroundTasks. If SMTP fails, login still
succeeds — the welcome is best-effort and intentionally not retried.
"""

from __future__ import annotations

import logging

from fastapi import BackgroundTasks

from ..db import acquire
from ..email_templates import welcome_html, welcome_text
from ..mailer import get_mailer

_log = logging.getLogger(__name__)


async def upsert_owner_and_maybe_welcome(
    email: str, name: str | None, bg: BackgroundTasks
) -> str:
    """Insert (or no-op) an owner row, return the owner_id, and queue a
    welcome email iff this is the first time we've seen this email.

    The welcomed_at update happens synchronously (atomic with the upsert)
    so a concurrent second login won't double-fire the email.
    """
    async with acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                INSERT INTO owners (email) VALUES ($1)
                ON CONFLICT (email) DO UPDATE SET email = EXCLUDED.email
                RETURNING owner_id, welcomed_at
                """,
                email,
            )
            assert row is not None  # RETURNING always yields a row
            should_welcome = row["welcomed_at"] is None
            if should_welcome:
                await conn.execute(
                    "UPDATE owners SET welcomed_at = now() WHERE owner_id = $1",
                    row["owner_id"],
                )

    if should_welcome:
        bg.add_task(_send_welcome_safely, email, name or "")
    return row["owner_id"]


async def _send_welcome_safely(email: str, name: str) -> None:
    """Background task — never raises. Failures are logged at WARN."""
    try:
        mailer = get_mailer()
        if not mailer.configured:
            _log.info("welcome_email_skipped reason=mailer_not_configured email=%s", email)
            return
        ok = await mailer.send(
            to=email,
            subject="Welcome to Margin",
            html=welcome_html(name),
            text=welcome_text(name),
        )
        if not ok:
            _log.warning("welcome_email_send_returned_false email=%s", email)
    except Exception as e:
        _log.warning("welcome_email_failed email=%s err=%r", email, e)
