"""Branded email templates for Margin.

Inline styles only — most email clients (Gmail, Outlook, Apple Mail) ignore
external stylesheets. Color tokens mirror the dashboard's CSS variables in
``apps/web/src/app/globals.css``.
"""

from __future__ import annotations

from .config import get_settings

# Brand tokens (matches apps/web/src/app/globals.css)
_BG = "#0b0d10"
_CARD_BG = "#131619"
_FG = "#e8e6e3"
_MUTED = "#8a8e93"
_ACCENT = "#f5dd5b"
_LINE = "#1f2227"


def _first_name(name: str) -> str:
    """Best-effort first-name extraction. Falls back to the whole string."""
    name = (name or "").strip()
    if not name:
        return "there"
    return name.split()[0]


def welcome_text(name: str) -> str:
    """Plaintext fallback for the welcome email."""
    first = _first_name(name)
    settings = get_settings()
    return (
        f"Welcome to Margin, {first}.\n"
        f"\n"
        f"Margin gives Claude a persistent research workspace — every claim cited,\n"
        f"every page archived. Mint an API key, drop the MCP URL into Claude.ai's\n"
        f"connector, and your agent gets eight new primitives.\n"
        f"\n"
        f"Open the dashboard: {settings.public_base_url}/app\n"
        f"\n"
        f"-- Margin\n"
    )


def welcome_html(name: str) -> str:
    """Branded HTML body for the welcome email. Table-based for Outlook."""
    first = _first_name(name)
    settings = get_settings()
    dashboard_url = f"{settings.public_base_url}/app"
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Welcome to Margin</title>
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
          <td style="color:{_FG};font-size:20px;font-weight:600;line-height:1.3;padding:0 0 12px 0;">
            Welcome, {first}.
          </td>
        </tr>
        <tr>
          <td style="color:{_FG};font-size:15px;line-height:1.6;padding:0 0 28px 0;">
            Margin gives Claude a persistent research workspace — every claim cited, every page archived. Mint an API key, drop the MCP URL into Claude.ai's connector, and your agent gets eight new primitives.
          </td>
        </tr>
        <tr>
          <td style="background:{_CARD_BG};border:1px solid {_LINE};border-radius:8px;padding:24px;">
            <a href="{dashboard_url}" style="display:inline-block;background:{_ACCENT};color:#000;text-decoration:none;font-weight:600;font-size:14px;padding:10px 18px;border-radius:6px;">
              Open the dashboard
            </a>
            <div style="color:{_MUTED};font-size:13px;line-height:1.6;padding-top:16px;">
              Or paste this URL: <a href="{dashboard_url}" style="color:{_MUTED};text-decoration:underline;">{dashboard_url}</a>
            </div>
          </td>
        </tr>
        <tr>
          <td style="border-top:1px solid {_LINE};margin-top:32px;padding:32px 0 0 0;color:{_MUTED};font-size:12px;line-height:1.5;">
            Margin — the research workspace for AI agents.
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>
</body>
</html>
"""
