"""Project create/list/branch and ownership scoping."""

import pytest


@pytest.mark.asyncio
async def test_create_and_list_projects(client, agent):
    _, _, key = agent
    headers = {"Authorization": f"Bearer {key}"}

    r = await client.post(
        "/v1/projects",
        json={"topic": "the topic", "depth": "thorough"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    pid = r.json()["project_id"]
    assert pid.startswith("p_")

    r2 = await client.get("/v1/projects", headers=headers)
    assert r2.status_code == 200
    body = r2.json()
    assert body["total"] >= 1
    assert any(p["project_id"] == pid for p in body["projects"])


@pytest.mark.asyncio
async def test_branch_inherits_topic_and_sets_parent(client, agent):
    _, _, key = agent
    headers = {"Authorization": f"Bearer {key}"}
    p = (
        await client.post(
            "/v1/projects",
            json={"topic": "the parent topic", "depth": "standard"},
            headers=headers,
        )
    ).json()
    b = await client.post(
        f"/v1/projects/{p['project_id']}/branches",
        json={"reason": "chase a contradiction"},
        headers=headers,
    )
    assert b.status_code == 201, b.text
    body = b.json()
    assert body["parent_id"] == p["project_id"]
    assert body["topic"] == p["topic"]


@pytest.mark.asyncio
async def test_other_agents_cannot_see_projects(client, agent, db_pool):
    _, _, key1 = agent
    # Create a second agent
    import bcrypt
    import secrets

    plaintext2 = "ag_live_" + secrets.token_hex(12)
    h = bcrypt.hashpw(plaintext2.encode(), bcrypt.gensalt(rounds=4)).decode()
    async with db_pool.acquire() as conn:
        owner_id = await conn.fetchval(
            "INSERT INTO owners (email) VALUES ('other@margin.dev') RETURNING owner_id"
        )
        await conn.execute(
            "INSERT INTO agents (owner_id, name, key_hash, key_prefix) VALUES ($1, 'Other', $2, $3)",
            owner_id,
            h,
            plaintext2[:12],
        )

    p = (
        await client.post(
            "/v1/projects",
            json={"topic": "ours", "depth": "standard"},
            headers={"Authorization": f"Bearer {key1}"},
        )
    ).json()

    r = await client.get(
        "/v1/projects",
        headers={"Authorization": f"Bearer {plaintext2}"},
    )
    assert r.status_code == 200
    other_pids = {x["project_id"] for x in r.json()["projects"]}
    assert p["project_id"] not in other_pids


@pytest.mark.asyncio
async def test_unauthorized_returns_401(client):
    r = await client.get("/v1/projects")
    assert r.status_code == 401
    r2 = await client.get(
        "/v1/projects", headers={"Authorization": "Bearer bogus"}
    )
    assert r2.status_code == 401
