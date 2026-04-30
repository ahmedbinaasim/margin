"""Branded email templates for Margin.

Inline styles only — most email clients (Gmail, Outlook, Apple Mail) ignore
external stylesheets. Color tokens mirror the dashboard's CSS variables in
``apps/web/src/app/globals.css``.
"""

from __future__ import annotations

# Brand tokens (matches apps/web/src/app/globals.css)
_BG = "#0b0d10"
_CARD_BG = "#131619"
_FG = "#e8e6e3"
_MUTED = "#8a8e93"
_ACCENT = "#f5dd5b"
_LINE = "#1f2227"


def magic_link_text(code: str, ttl_min: int) -> str:
    """Plaintext fallback. Multipart-friendly."""
    return (
        f"Your Margin sign-in code is: {code}\n"
        f"\n"
        f"It expires in {ttl_min} minutes.\n"
        f"\n"
        f"Didn't request this? Ignore this email.\n"
        f"\n"
        f"-- Margin\n"
    )


def magic_link_html(code: str, ttl_min: int) -> str:
    """Branded HTML body. Table-based for Outlook compatibility."""
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Your Margin sign-in code</title>
</head>
<body style="margin:0;padding:0;background:{_BG};font-family:ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,sans-serif;">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:{_BG};padding:40px 16px;">
  <tr>
    <td align="center">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="max-width:480px;background:{_BG};">
        <tr>
          <td style="padding:0 0 32px 0;">
            <span style="font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:22px;font-weight:600;letter-spacing:-0.02em;color:{_ACCENT};">Margin</span>
          </td>
        </tr>
        <tr>
          <td style="color:{_FG};font-size:15px;line-height:1.6;padding:0 0 24px 0;">
            Your sign-in code is below. Paste it into the dashboard to continue.
          </td>
        </tr>
        <tr>
          <td style="background:{_CARD_BG};border:1px solid {_LINE};border-radius:8px;padding:28px 16px;">
            <div style="font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:34px;font-weight:600;letter-spacing:0.32em;color:{_ACCENT};text-align:center;">
              {code}
            </div>
          </td>
        </tr>
        <tr>
          <td style="color:{_MUTED};font-size:13px;line-height:1.6;padding:24px 0 0 0;">
            Expires in {ttl_min} minutes. Didn't request this? Ignore this email — no action will be taken.
          </td>
        </tr>
        <tr>
          <td style="border-top:1px solid {_LINE};margin-top:32px;padding:32px 0 0 0;color:{_MUTED};font-size:12px;line-height:1.5;">
            Margin — the research workspace for AI agents.<br>
            <a href="https://margin.dev" style="color:{_MUTED};text-decoration:underline;">margin.dev</a>
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>
</body>
</html>
"""
