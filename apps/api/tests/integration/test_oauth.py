"""End-to-end OAuth 2.1 + DCR flow.

Stubs Firebase verification so we can mint an owner JWT, then walks the full
OAuth dance: register client → sign auth_request → /authorize-decision →
exchange code → verify access token → refresh → confirm rotation kills the
previous refresh token. Also exercises the negative paths: bad PKCE, expired/
re-used codes, wrong audience.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
from urllib.parse import parse_qs, urlparse

import jwt
import pytest

from margin_api import routes_rest
from margin_api.config import get_settings
from margin_api.oauth.state import sign_auth_request
from margin_api.oauth.tokens import mcp_audience, verify_access_token


def _stub_firebase(decoded: dict):
    def _f(_token: str) -> dict:
        return decoded

    return _f


def _pkce_pair() -> tuple[str, str]:
    """Generate a code_verifier + S256 code_challenge."""
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


async def _sign_in_owner(client, monkeypatch, email: str = "owner@margin.dev") -> str:
    monkeypatch.setattr(
        routes_rest,
        "verify_google_id_token",
        _stub_firebase({"email": email, "email_verified": True, "name": "Test"}),
    )
    r = await client.post("/v1/auth/firebase", json={"id_token": "fake"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


async def _register_client(client) -> str:
    r = await client.post(
        "/oauth/register",
        json={
            "client_name": "Test MCP Client",
            "redirect_uris": ["http://localhost:9999/cb"],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["client_id"]


@pytest.mark.asyncio
async def test_full_oauth_flow_happy_path(client, db_pool, monkeypatch):
    owner_token = await _sign_in_owner(client, monkeypatch)
    client_id = await _register_client(client)

    # The /authorize endpoint redirects to the dashboard with a signed blob.
    # We can also synthesize the blob directly to skip the 302 hop in tests.
    verifier, challenge = _pkce_pair()
    auth_request = sign_auth_request(
        client_id=client_id,
        redirect_uri="http://localhost:9999/cb",
        code_challenge=challenge,
        code_challenge_method="S256",
        state="opaque-state",
        scope=None,
        resource=mcp_audience(),
    )

    # Owner approves
    r = await client.post(
        "/v1/oauth/authorize-decision",
        json={"decision": "allow", "auth_request": auth_request},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert r.status_code == 200, r.text
    redirect_to = r.json()["redirect_to"]
    qs = parse_qs(urlparse(redirect_to).query)
    code = qs["code"][0]
    assert qs["state"][0] == "opaque-state"

    # Exchange code for token
    r = await client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": "http://localhost:9999/cb",
            "client_id": client_id,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token_type"] == "Bearer"
    assert body["expires_in"] == 3600
    access_token = body["access_token"]
    refresh_token = body["refresh_token"]

    # Access token must validate against the canonical /mcp audience
    claims = verify_access_token(access_token)
    assert claims is not None
    assert claims["sub"].startswith("ag_")
    assert claims["scope"] == "mcp"
    assert claims["client_id"] == client_id
    assert claims["aud"] == mcp_audience()

    # Refresh token rotates: using it returns a new pair, and the old one stops working.
    r = await client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 200, r.text
    new_body = r.json()
    assert new_body["refresh_token"] != refresh_token
    assert new_body["access_token"] != access_token

    # Old refresh token now rejected
    r = await client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_grant"


@pytest.mark.asyncio
async def test_pkce_failure(client, db_pool, monkeypatch):
    owner_token = await _sign_in_owner(client, monkeypatch, email="pkce@margin.dev")
    client_id = await _register_client(client)

    verifier, challenge = _pkce_pair()
    auth_request = sign_auth_request(
        client_id=client_id,
        redirect_uri="http://localhost:9999/cb",
        code_challenge=challenge,
        code_challenge_method="S256",
        state=None,
        scope=None,
        resource=mcp_audience(),
    )
    r = await client.post(
        "/v1/oauth/authorize-decision",
        json={"decision": "allow", "auth_request": auth_request},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    code = parse_qs(urlparse(r.json()["redirect_to"]).query)["code"][0]

    # Wrong verifier — should fail PKCE check
    bad = await client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": verifier + "tampered",
            "redirect_uri": "http://localhost:9999/cb",
            "client_id": client_id,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert bad.status_code == 400
    assert bad.json()["error"] == "invalid_grant"


@pytest.mark.asyncio
async def test_code_single_use(client, db_pool, monkeypatch):
    owner_token = await _sign_in_owner(client, monkeypatch, email="single@margin.dev")
    client_id = await _register_client(client)

    verifier, challenge = _pkce_pair()
    auth_request = sign_auth_request(
        client_id=client_id,
        redirect_uri="http://localhost:9999/cb",
        code_challenge=challenge,
        code_challenge_method="S256",
        state=None,
        scope=None,
        resource=mcp_audience(),
    )
    r = await client.post(
        "/v1/oauth/authorize-decision",
        json={"decision": "allow", "auth_request": auth_request},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    code = parse_qs(urlparse(r.json()["redirect_to"]).query)["code"][0]

    form = {
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": verifier,
        "redirect_uri": "http://localhost:9999/cb",
        "client_id": client_id,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    first = await client.post("/oauth/token", data=form, headers=headers)
    assert first.status_code == 200

    # Second use must be rejected as `invalid_grant`
    second = await client.post("/oauth/token", data=form, headers=headers)
    assert second.status_code == 400
    assert second.json()["error"] == "invalid_grant"


@pytest.mark.asyncio
async def test_wrong_audience_rejected_by_verifier():
    """Tokens signed with our secret but for a different aud must NOT validate
    on the /mcp resource path."""
    settings = get_settings()
    now = int(time.time())
    bogus = jwt.encode(
        {
            "iss": settings.api_base_url,
            "sub": "ag_bogus",
            "aud": "https://api.margin.dev/some-other-resource",
            "iat": now,
            "exp": now + 60,
            "scope": "mcp",
            "owner_id": "o_x",
            "client_id": "cli_x",
            "token_type": "access",
        },
        settings.jwt_secret,
        algorithm="HS256",
    )
    assert verify_access_token(bogus) is None


@pytest.mark.asyncio
async def test_authorize_rejects_unknown_client(client):
    r = await client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": "cli_doesnotexist",
            "redirect_uri": "http://localhost:9999/cb",
            "code_challenge": "x" * 43,
            "code_challenge_method": "S256",
        },
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_register_rejects_non_https_redirect(client):
    r = await client.post(
        "/oauth/register",
        json={
            "client_name": "Bad Client",
            "redirect_uris": ["http://evil.example.com/cb"],
        },
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_well_known_endpoints_exposed(client):
    r1 = await client.get("/.well-known/oauth-protected-resource")
    assert r1.status_code == 200
    assert mcp_audience() == r1.json()["resource"]

    r2 = await client.get("/.well-known/oauth-authorization-server")
    assert r2.status_code == 200
    body = r2.json()
    assert "S256" in body["code_challenge_methods_supported"]
    assert body["registration_endpoint"].endswith("/oauth/register")
