"""Firebase Google sign-in flow + agent minting + agent key bcrypt verification.

`verify_google_id_token` is monkeypatched so the test never hits the Firebase
Admin SDK; we just feed in the decoded-claims dict it would normally return.
"""

from __future__ import annotations

import pytest

from margin_api import routes_rest


def _stub_verify(decoded: dict):
    def _f(_token: str) -> dict:
        return decoded

    return _f


@pytest.mark.asyncio
async def test_firebase_flow_mints_jwt_and_agent(client, db_pool, monkeypatch):
    monkeypatch.setattr(
        routes_rest,
        "verify_google_id_token",
        _stub_verify({"email": "magic@margin.dev", "email_verified": True, "name": "Magic"}),
    )

    r = await client.post("/v1/auth/firebase", json={"id_token": "fake.id.token"})
    assert r.status_code == 200, r.text
    token = r.json()["token"]

    me = await client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "magic@margin.dev"

    # Mint an agent
    mk = await client.post(
        "/v1/agents",
        json={"name": "Sara's Claude Desktop"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert mk.status_code == 200, mk.text
    body = mk.json()
    assert body["api_key"].startswith("ag_live_")
    assert body["mcp_url"].endswith(body["api_key"])

    # The plaintext key now authenticates against the agent endpoints.
    r = await client.get(
        "/v1/projects", headers={"Authorization": f"Bearer {body['api_key']}"}
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_firebase_invalid_token_rejected(client, monkeypatch):
    from fastapi import HTTPException, status

    def _reject(_token: str) -> dict:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="firebase token invalid"
        )

    monkeypatch.setattr(routes_rest, "verify_google_id_token", _reject)
    r = await client.post("/v1/auth/firebase", json={"id_token": "bogus"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_welcome_only_fires_once(client, db_pool, monkeypatch):
    """Second login for the same email must not re-mark welcomed_at."""
    monkeypatch.setattr(
        routes_rest,
        "verify_google_id_token",
        _stub_verify({"email": "once@margin.dev", "email_verified": True, "name": "Once"}),
    )

    r1 = await client.post("/v1/auth/firebase", json={"id_token": "t1"})
    assert r1.status_code == 200

    async with db_pool.acquire() as conn:
        first = await conn.fetchval(
            "SELECT welcomed_at FROM owners WHERE email = $1", "once@margin.dev"
        )

    r2 = await client.post("/v1/auth/firebase", json={"id_token": "t2"})
    assert r2.status_code == 200

    async with db_pool.acquire() as conn:
        second = await conn.fetchval(
            "SELECT welcomed_at FROM owners WHERE email = $1", "once@margin.dev"
        )

    assert first is not None
    assert first == second  # untouched on second sign-in
