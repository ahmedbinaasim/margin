"""Generic SMTP mailer — nodemailer-style.

Build the transporter once per process (with config from env), then call
``send(to=..., subject=..., html=..., text=...)`` from anywhere. Used today
for the welcome email; trivially extends to any future transactional mail.

Provider-agnostic: any SMTP server works (Gmail, Resend, Brevo, SMTP2GO,
Mailgun) by setting SMTP_HOST/PORT/USERNAME/PASSWORD/etc. Picks STARTTLS
when ``SMTP_START_TLS=true`` (recommended; works on Render free tier),
implicit TLS when ``SMTP_USE_TLS=true``.

``send`` never raises — it logs and returns False — because callers run it
in FastAPI ``BackgroundTasks`` where a raise wouldn't surface anyway.
"""

from __future__ import annotations

import logging
from email.message import EmailMessage

from .config import Settings, get_settings

_log = logging.getLogger(__name__)


class Mailer:
    """Single configurable SMTP transporter. Reusable across email types."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def configured(self) -> bool:
        """True iff host + password are set. Otherwise ``send`` is a no-op."""
        return bool(self._settings.smtp_host and self._settings.smtp_password)

    async def send(self, *, to: str, subject: str, html: str, text: str) -> bool:
        """Send a multipart MIME email. Returns True on success, False on any
        failure. Never raises.
        """
        if not self.configured:
            return False

        try:
            import aiosmtplib

            msg = EmailMessage()
            msg["From"] = self._settings.smtp_from
            msg["To"] = to
            msg["Subject"] = subject
            msg.set_content(text)
            msg.add_alternative(html, subtype="html")

            kwargs: dict[str, object] = {
                "hostname": self._settings.smtp_host,
                "port": self._settings.smtp_port,
                "username": self._settings.smtp_username,
                "password": self._settings.smtp_password,
                "timeout": self._settings.smtp_timeout,
            }
            # aiosmtplib forbids both flags being True; pick exactly one.
            if self._settings.smtp_start_tls:
                kwargs["start_tls"] = True
            elif self._settings.smtp_use_tls:
                kwargs["use_tls"] = True

            await aiosmtplib.send(msg, **kwargs)
            return True
        except Exception as e:
            _log.warning("smtp_send_failed to=%s subject=%s err=%r", to, subject, e)
            return False


_mailer: Mailer | None = None


def get_mailer() -> Mailer:
    global _mailer
    if _mailer is None:
        _mailer = Mailer(get_settings())
    return _mailer


def reset_mailer() -> None:
    """For tests."""
    global _mailer
    _mailer = None
