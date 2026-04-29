"""add_finding idempotency on (project_id, content_hash)."""

import pytest


@pytest.mark.asyncio
async def test_dedup_returns_same_finding_id(client, agent):
    _, _, key = agent
    h = {"Authorization": f"Bearer {key}"}
    p = (await client.post("/v1/projects", json={"topic": "t", "depth": "quick"}, headers=h)).json()
    body = {
        "claim": "X is true",
        "evidence": "evidence",
        "confidence": 0.9,
        "source": "https://example.com",
    }
    r1 = await client.post(f"/v1/projects/{p['project_id']}/findings", json=body, headers=h)
    assert r1.status_code == 201, r1.text
    f1 = r1.json()
    assert f1["deduped"] is False

    r2 = await client.post(f"/v1/projects/{p['project_id']}/findings", json=body, headers=h)
    assert r2.status_code == 201
    f2 = r2.json()
    assert f2["deduped"] is True
    assert f2["finding_id"] == f1["finding_id"]


@pytest.mark.asyncio
async def test_dedup_is_per_project(client, agent):
    _, _, key = agent
    h = {"Authorization": f"Bearer {key}"}
    p1 = (await client.post("/v1/projects", json={"topic": "p1", "depth": "quick"}, headers=h)).json()
    p2 = (await client.post("/v1/projects", json={"topic": "p2", "depth": "quick"}, headers=h)).json()
    body = {"claim": "Z", "evidence": "ev", "confidence": 0.5}
    f1 = (await client.post(f"/v1/projects/{p1['project_id']}/findings", json=body, headers=h)).json()
    f2 = (await client.post(f"/v1/projects/{p2['project_id']}/findings", json=body, headers=h)).json()
    assert f1["finding_id"] != f2["finding_id"]
    assert f1["deduped"] is False
    assert f2["deduped"] is False


@pytest.mark.asyncio
async def test_contradicts_must_be_in_same_project(client, agent):
    _, _, key = agent
    h = {"Authorization": f"Bearer {key}"}
    p1 = (await client.post("/v1/projects", json={"topic": "p1", "depth": "quick"}, headers=h)).json()
    p2 = (await client.post("/v1/projects", json={"topic": "p2", "depth": "quick"}, headers=h)).json()
    f1 = (
        await client.post(
            f"/v1/projects/{p1['project_id']}/findings",
            json={"claim": "A", "evidence": "ev1", "confidence": 0.8},
            headers=h,
        )
    ).json()
    r = await client.post(
        f"/v1/projects/{p2['project_id']}/findings",
        json={
            "claim": "B",
            "evidence": "ev2",
            "confidence": 0.7,
            "contradicts": f1["finding_id"],
        },
        headers=h,
    )
    assert r.status_code == 409, r.text
