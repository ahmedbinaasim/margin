"""OAuth 2.1 + Dynamic Client Registration for the MCP transport.

Margin acts as both Authorization Server (issues tokens) and Resource Server
(validates them on /mcp). Clients register dynamically (RFC 7591), the user
consents in the dashboard, and we issue short-lived JWT access tokens
(audience-bound to /mcp) plus rotating opaque refresh tokens.
"""
