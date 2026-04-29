"""Markdown rendering and confidence bucketing."""

import pytest


@pytest.mark.asyncio
async def test_publish_groups_findings_by_confidence(client, agent):
    _, _, key = agent
    h = {"Authorization": f"Bearer {key}"}
    p = (await client.post("/v1/projects", json={"topic": "the topic", "depth": "thorough"}, headers=h)).json()

    pid = p["project_id"]
    facts = [
        ("Confirmed claim A", 0.95),
        ("Confirmed claim B", 0.8),
        ("Tentative claim C", 0.5),
    ]
    for c, conf in facts:
        await client.post(
            f"/v1/projects/{pid}/findings",
            json={"claim": c, "evidence": c + " ev", "confidence": conf},
            headers=h,
        )

    r = await client.post(
        f"/v1/projects/{pid}/reports", json={"format": "markdown"}, headers=h
    )
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["public_slug"] == pid
    assert out["report_url"].endswith(f"/r/{pid}")

    # Public fetch (no auth required)
    pr = await client.get(f"/v1/reports/{pid}")
    assert pr.status_code == 200
    body = pr.json()["body"]
    assert "Confirmed (confidence" in body
    assert "Tentative (confidence" in body
    assert "Confirmed claim A" in body
    assert "Tentative claim C" in body


@pytest.mark.asyncio
async def test_publish_json_format(client, agent):
    _, _, key = agent
    h = {"Authorization": f"Bearer {key}"}
    p = (await client.post("/v1/projects", json={"topic": "test topic", "depth": "quick"}, headers=h)).json()
    await client.post(
        f"/v1/projects/{p['project_id']}/findings",
        json={"claim": "claim X", "evidence": "evidence", "confidence": 0.9},
        headers=h,
    )
    r = await client.post(
        f"/v1/projects/{p['project_id']}/reports",
        json={"format": "json"},
        headers=h,
    )
    assert r.status_code == 201
    pub = await client.get(f"/v1/reports/{p['project_id']}")
    assert pub.status_code == 200
    import json

    obj = json.loads(pub.json()["body"])
    assert obj["topic"] == "test topic"
    assert any(f["claim"] == "claim X" for f in obj["findings"])
