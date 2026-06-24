"""OAuth 2.1 + DCR endpoints.

The full set:

  GET  /.well-known/oauth-protected-resource    — RFC 9728
  GET  /.well-known/oauth-authorization-server  — RFC 8414
  POST /oauth/register                          — RFC 7591 (DCR)
  GET  /oauth/authorize                         — auth request validator + redirect
  POST /oauth/token                             — code exchange + refresh
  GET  /v1/oauth/clients/{client_id}            — consent UI lookup (owner JWT)
  POST /v1/oauth/authorize-decision             — owner approves/denies (owner JWT)

Public clients with PKCE (S256) only. No client secrets.
"""

from __future__ import annotations

import base64
import hashlib
import logging
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from .. import models as m
from ..auth import OwnerDep
from ..config import get_settings
from ..services import agents as agents_svc
from . import services as oauth_svc
from .state import sign_auth_request, verify_auth_request
from .tokens import issue_access_token, mcp_audience

_log = logging.getLogger(__name__)


# Two routers: one for the public OAuth + discovery endpoints (mounted at root)
# and one for the owner-authenticated endpoints (mounted at /v1).
public_router = APIRouter(tags=["oauth"])
owner_router = APIRouter(prefix="/v1/oauth", tags=["oauth"])


# ------------------------------ Discovery ------------------------------------


@public_router.get("/.well-known/oauth-protected-resource")
async def protected_resource_metadata() -> dict:
    """RFC 9728 — advertises which AS protects the /mcp resource."""
    settings = get_settings()
    return {
        "resource": mcp_audience(),
        "authorization_servers": [settings.api_base_url],
        "scopes_supported": ["mcp"],
        "bearer_methods_supported": ["header"],
    }


@public_router.get("/.well-known/oauth-authorization-server")
async def authorization_server_metadata() -> dict:
    """RFC 8414 — what endpoints + capabilities the AS exposes."""
    settings = get_settings()
    base = settings.api_base_url
    return {
        "issuer": base,
        "authorization_endpoint": f"{base}/oauth/authorize",
        "token_endpoint": f"{base}/oauth/token",
        "registration_endpoint": f"{base}/oauth/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "scopes_supported": ["mcp"],
        "service_documentation": f"{settings.public_base_url}/docs",
    }


# ------------------------------ DCR ------------------------------------------


def _is_safe_redirect(uri: str) -> bool:
    """Allow https:// or http://localhost / 127.0.0.1 only."""
    if uri.startswith("https://"):
        return True
    if uri.startswith("http://localhost") or uri.startswith("http://127.0.0.1"):
        return True
    return False


@public_router.post(
    "/oauth/register",
    response_model=m.OAuthClientResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_client(body: m.OAuthClientRegistrationInput) -> m.OAuthClientResponse:
    """RFC 7591 dynamic client registration."""
    for uri in body.redirect_uris:
        if not _is_safe_redirect(uri):
            raise HTTPException(
                status_code=400,
                detail="redirect_uris must use https:// or http://localhost",
            )
    if body.token_endpoint_auth_method != "none":
        raise HTTPException(
            status_code=400,
            detail="only token_endpoint_auth_method='none' (PKCE) is supported",
        )

    row = await oauth_svc.register_client(
        client_name=body.client_name,
        redirect_uris=body.redirect_uris,
        grant_types=body.grant_types,
        response_types=body.response_types,
        token_endpoint_auth_method=body.token_endpoint_auth_method,
        logo_uri=body.logo_uri,
        client_uri=body.client_uri,
        software_id=body.software_id,
        software_version=body.software_version,
    )
    return m.OAuthClientResponse(**row)


# ------------------------------ Authorize ------------------------------------


def _error_html(detail: str) -> HTMLResponse:
    body = (
        "<!doctype html><meta charset=utf-8>"
        "<title>Margin — Authorization Error</title>"
        "<body style='background:#0b0d10;color:#e8e6e3;font-family:ui-sans-serif,system-ui;"
        "padding:48px;max-width:480px;margin:0 auto;'>"
        f"<h1 style='color:#f5dd5b;font-size:20px;'>Margin</h1>"
        f"<p style='color:#ffaa66;'>Authorization request rejected.</p>"
        f"<p style='color:#8a8e93;font-size:14px;'>{detail}</p>"
        "</body>"
    )
    return HTMLResponse(content=body, status_code=400)


@public_router.get("/oauth/authorize")
async def authorize(
    response_type: Annotated[str, Query()],
    client_id: Annotated[str, Query()],
    redirect_uri: Annotated[str, Query()],
    code_challenge: Annotated[str, Query()],
    code_challenge_method: Annotated[str, Query()] = "S256",
    resource: Annotated[str | None, Query()] = None,
    scope: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
):
    """Validate the authorization request and 302 to the dashboard consent UI.

    No code is generated here — the dashboard re-validates and POSTs to
    /v1/oauth/authorize-decision after the user clicks Approve.
    """
    if response_type != "code":
        return _error_html("response_type must be 'code'")
    if code_challenge_method != "S256":
        return _error_html("code_challenge_method must be 'S256'")
    if not code_challenge:
        return _error_html("code_challenge is required")

    client = await oauth_svc.get_client(client_id)
    if client is None:
        return _error_html(f"unknown client_id {client_id!r}")
    if redirect_uri not in client["redirect_uris"]:
        return _error_html("redirect_uri does not match the registered client")

    # MCP spec mandates the resource parameter for tokens that target /mcp.
    expected_resource = mcp_audience()
    if resource is not None and resource.rstrip("/") != expected_resource.rstrip("/"):
        return _error_html(
            f"resource must be {expected_resource}; got {resource!r}"
        )
    resolved_resource = resource or expected_resource

    blob = sign_auth_request(
        client_id=client_id,
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        state=state,
        scope=scope,
        resource=resolved_resource,
    )
    settings = get_settings()
    consent_url = f"{settings.public_base_url}/app/authorize?{urlencode({'auth_request': blob})}"
    return RedirectResponse(consent_url, status_code=302)


# ------------------- Owner-authenticated endpoints ---------------------------


@owner_router.get("/clients/{client_id}", response_model=m.OAuthClientResponse)
async def get_client_for_consent(client_id: str, owner: OwnerDep) -> m.OAuthClientResponse:
    """Consent UI fetches client metadata to display name/logo. Owner-auth'd
    so we don't leak registered-client metadata to anonymous callers."""
    row = await oauth_svc.get_client(client_id)
    if row is None:
        raise HTTPException(status_code=404, detail="client not found")
    return m.OAuthClientResponse(**row)


@owner_router.post("/authorize-decision", response_model=m.OAuthAuthorizeDecisionOutput)
async def authorize_decision(
    body: m.OAuthAuthorizeDecisionInput, owner: OwnerDep
) -> m.OAuthAuthorizeDecisionOutput:
    """Apply the user's approve/deny decision and produce the redirect URL."""
    payload = verify_auth_request(body.auth_request)
    if payload is None:
        raise HTTPException(status_code=400, detail="auth_request invalid or expired")

    redirect_uri: str = payload["redirect_uri"]
    state: str | None = payload.get("state")

    if body.decision == "deny":
        params = {"error": "access_denied"}
        if state:
            params["state"] = state
        sep = "&" if "?" in redirect_uri else "?"
        return m.OAuthAuthorizeDecisionOutput(
            redirect_to=f"{redirect_uri}{sep}{urlencode(params)}"
        )

    # decision == "allow" — re-validate the client and mint resources.
    client = await oauth_svc.get_client(payload["client_id"])
    if client is None:
        raise HTTPException(status_code=400, detail="client no longer registered")
    if redirect_uri not in client["redirect_uris"]:
        raise HTTPException(status_code=400, detail="redirect_uri no longer matches")

    # Mint a fresh agent for this client. The plaintext key is discarded —
    # OAuth-minted agents authenticate via JWT, not URL-keys. (The agent row
    # still has key_hash/key_prefix populated, harmless and keeps the schema
    # uniform.)
    suggested_name = f"{client['client_name']} (OAuth)"
    agent_row, _key = await agents_svc.create_agent_for_owner(
        owner.owner_id, suggested_name
    )

    code = await oauth_svc.create_authorization_code(
        client_id=payload["client_id"],
        owner_id=owner.owner_id,
        agent_id=agent_row["agent_id"],
        redirect_uri=redirect_uri,
        code_challenge=payload["code_challenge"],
        code_challenge_method=payload["code_challenge_method"],
        scope=payload.get("scope"),
        resource=payload.get("resource"),
    )
    params = {"code": code}
    if state:
        params["state"] = state
    sep = "&" if "?" in redirect_uri else "?"
    return m.OAuthAuthorizeDecisionOutput(
        redirect_to=f"{redirect_uri}{sep}{urlencode(params)}"
    )


# ------------------------------ Token ----------------------------------------


def _pkce_matches(verifier: str, challenge: str) -> bool:
    """S256: BASE64URL(SHA256(verifier)) == challenge."""
    digest = hashlib.sha256(verifier.encode()).digest()
    expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return expected == challenge


def _token_error(error: str, detail: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse(
        {"error": error, "error_description": detail}, status_code=status_code
    )


@public_router.post("/oauth/token")
async def token_endpoint(
    request: Request,
    grant_type: Annotated[str, Form()],
    client_id: Annotated[str, Form()],
    code: Annotated[str | None, Form()] = None,
    code_verifier: Annotated[str | None, Form()] = None,
    redirect_uri: Annotated[str | None, Form()] = None,
    refresh_token: Annotated[str | None, Form()] = None,
    resource: Annotated[str | None, Form()] = None,
):
    """Token endpoint. Accepts form-encoded body per OAuth standard.

    Two grants:
      - authorization_code: exchange a code + verifier for tokens
      - refresh_token: rotate refresh, return a fresh access token
    """
    if grant_type == "authorization_code":
        if not (code and code_verifier and redirect_uri):
            return _token_error("invalid_request", "code, code_verifier, and redirect_uri are required")

        bindings = await oauth_svc.consume_authorization_code(code)
        if bindings is None:
            return _token_error("invalid_grant", "code invalid, expired, or already used")
        if bindings["client_id"] != client_id:
            return _token_error("invalid_grant", "client_id mismatch")
        if bindings["redirect_uri"] != redirect_uri:
            return _token_error("invalid_grant", "redirect_uri mismatch")
        if not _pkce_matches(code_verifier, bindings["code_challenge"]):
            return _token_error("invalid_grant", "PKCE verification failed")

        access_token, expires_in = issue_access_token(
            agent_id=bindings["agent_id"],
            owner_id=bindings["owner_id"],
            client_id=client_id,
            scope=bindings.get("scope") or "mcp",
        )
        refresh = await oauth_svc.issue_refresh_token(
            client_id=client_id,
            agent_id=bindings["agent_id"],
            owner_id=bindings["owner_id"],
            scope=bindings.get("scope"),
        )
        return {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": expires_in,
            "refresh_token": refresh,
            "scope": bindings.get("scope") or "mcp",
        }

    if grant_type == "refresh_token":
        if not refresh_token:
            return _token_error("invalid_request", "refresh_token is required")

        bindings = await oauth_svc.consume_refresh_token(refresh_token, client_id=client_id)
        if bindings is None:
            return _token_error("invalid_grant", "refresh_token invalid, revoked, or expired")

        access_token, expires_in = issue_access_token(
            agent_id=bindings["agent_id"],
            owner_id=bindings["owner_id"],
            client_id=client_id,
            scope=bindings.get("scope") or "mcp",
        )
        new_refresh = await oauth_svc.issue_refresh_token(
            client_id=client_id,
            agent_id=bindings["agent_id"],
            owner_id=bindings["owner_id"],
            scope=bindings.get("scope"),
        )
        return {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": expires_in,
            "refresh_token": new_refresh,
            "scope": bindings.get("scope") or "mcp",
        }

    return _token_error("unsupported_grant_type", f"grant_type {grant_type!r} not supported")
