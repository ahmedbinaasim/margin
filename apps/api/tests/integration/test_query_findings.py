"""Semantic query returns rows ordered by cosine similarity."""

import pytest


@pytest.mark.asyncio
async def test_query_returns_results_under_filter(client, agent):
    _, _, key = agent
    h = {"Authorization": f"Bearer {key}"}
    p = (await client.post("/v1/projects", json={"topic": "test topic", "depth": "quick"}, headers=h)).json()

    facts = [
        ("Fly.io machines cold-start in seconds", 0.9),
        ("Render free sleeps after 15 minutes", 0.85),
        ("Cats purr at 25 Hz", 0.6),
    ]
    for claim, conf in facts:
        await client.post(
            f"/v1/projects/{p['project_id']}/findings",
            json={"claim": claim, "evidence": claim + " evidence", "confidence": conf},
            headers=h,
        )

    r = await client.post(
        f"/v1/projects/{p['project_id']}/query",
        json={"semantic_query": "cold start", "limit": 3, "min_confidence": 0.7},
        headers=h,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    # min_confidence filtered out the cat fact (0.6)
    claims = [r_["claim"] for r_ in body["results"]]
    assert all("Cats" not in c for c in claims)


@pytest.mark.asyncio
async def test_query_unauthorized_for_other_agent(client, agent, db_pool):
    _, _, key1 = agent
    h1 = {"Authorization": f"Bearer {key1}"}
    p = (await client.post("/v1/projects", json={"topic": "test topic", "depth": "quick"}, headers=h1)).json()

    import bcrypt
    import secrets

    plaintext2 = "ag_live_" + secrets.token_hex(12)
    hkey = bcrypt.hashpw(plaintext2.encode(), bcrypt.gensalt(rounds=4)).decode()
    async with db_pool.acquire() as conn:
        owner_id = await conn.fetchval(
            "INSERT INTO owners (email) VALUES ('z@margin.dev') RETURNING owner_id"
        )
        await conn.execute(
            "INSERT INTO agents (owner_id, name, key_hash, key_prefix) VALUES ($1, 'Z', $2, $3)",
            owner_id,
            hkey,
            plaintext2[:12],
        )

    r = await client.post(
        f"/v1/projects/{p['project_id']}/query",
        json={"semantic_query": "the query", "limit": 5},
        headers={"Authorization": f"Bearer {plaintext2}"},
    )
    assert r.status_code == 404
