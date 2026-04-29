"""Magic-link sign-in flow + agent minting + agent key bcrypt verification."""

import pytest


@pytest.mark.asyncio
async def test_magic_link_dev_flow_mints_jwt_and_agent(client, db_pool):
    r1 = await client.post(
        "/v1/auth/request", json={"email": "magic@margin.dev"}
    )
    assert r1.status_code == 200, r1.text
    code = r1.json().get("dev_code")
    assert code is not None  # Resend not configured in tests
    r2 = await client.post(
        "/v1/auth/verify",
        json={"email": "magic@margin.dev", "code": code},
    )
    assert r2.status_code == 200
    token = r2.json()["token"]

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
    r = await client.get("/v1/projects", headers={"Authorization": f"Bearer {body['api_key']}"})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_invalid_code_rejected(client):
    await client.post("/v1/auth/request", json={"email": "x@margin.dev"})
    bad = await client.post(
        "/v1/auth/verify", json={"email": "x@margin.dev", "code": "000000"}
    )
    assert bad.status_code == 401


@pytest.mark.asyncio
async def test_used_code_cannot_be_reused(client):
    r1 = await client.post(
        "/v1/auth/request", json={"email": "y@margin.dev"}
    )
    code = r1.json()["dev_code"]
    a = await client.post(
        "/v1/auth/verify", json={"email": "y@margin.dev", "code": code}
    )
    assert a.status_code == 200
    b = await client.post(
        "/v1/auth/verify", json={"email": "y@margin.dev", "code": code}
    )
    assert b.status_code == 401
