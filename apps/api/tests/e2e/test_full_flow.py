"""End-to-end happy path against the in-process FastAPI app.

Walks the full agent journey: start_research → 5x add_finding → cite →
query_findings → branch_project → request_human_review → publish_report →
public report fetch.
"""

import httpx
import pytest
import respx


@pytest.mark.asyncio
@respx.mock(assert_all_called=False)
async def test_full_flow_rest(respx_mock, client, agent):
    _, _, key = agent
    h = {"Authorization": f"Bearer {key}"}

    # 1. start_research
    p = (
        await client.post(
            "/v1/projects",
            json={"topic": "free-tier MCP hosting in 2026", "depth": "thorough"},
            headers=h,
        )
    ).json()
    pid = p["project_id"]

    # 2. five findings, one duplicate
    facts = [
        ("Koyeb scales to zero after 1 hour idle", "Koyeb docs say 1 hour", 0.95),
        ("Render free sleeps after 15 minutes", "Render docs", 0.9),
        ("Neon free is never paused on inactivity", "Neon pricing page", 0.85),
        ("Cloudflare R2 has zero egress", "R2 pricing page", 0.92),
        ("Koyeb scales to zero after 1 hour idle", "Koyeb docs say 1 hour", 0.95),  # dup
    ]
    for claim, ev, conf in facts:
        await client.post(
            f"/v1/projects/{pid}/findings",
            json={"claim": claim, "evidence": ev, "confidence": conf},
            headers=h,
        )

    # 3. cite (mock the network)
    respx_mock.get("https://render.com/docs/free").mock(
        return_value=httpx.Response(
            200,
            content=b"<html><body><p>Free web services spin down after 15 minutes.</p></body></html>",
        )
    )
    findings = await client.get("/v1/projects", headers=h)
    # Use the first finding by introspecting the projects list count for sanity.
    list_proj = findings.json()
    assert any(p["project_id"] == pid for p in list_proj["projects"])

    # Fetch finding ids via query
    q = await client.post(
        f"/v1/projects/{pid}/query",
        json={"semantic_query": "Render", "limit": 1, "min_confidence": 0.0},
        headers=h,
    )
    assert q.status_code == 200
    rid = q.json()["results"][0]["finding_id"]

    cite = await client.post(
        f"/v1/findings/{rid}/citations",
        json={"url": "https://render.com/docs/free", "excerpt": "spin down"},
        headers=h,
    )
    assert cite.status_code == 201, cite.text
    assert cite.json()["fetch_status"] == 200

    # 4. query_findings
    q2 = await client.post(
        f"/v1/projects/{pid}/query",
        json={"semantic_query": "cold start", "limit": 5},
        headers=h,
    )
    assert q2.status_code == 200
    assert q2.json()["total"] >= 1

    # 5. branch_project
    b = await client.post(
        f"/v1/projects/{pid}/branches",
        json={"reason": "chase contradicting cold-start claims"},
        headers=h,
    )
    assert b.status_code == 201
    assert b.json()["parent_id"] == pid

    # 6. request_human_review
    rv = await client.post(
        f"/v1/projects/{pid}/reviews",
        json={"reason": "confidence on Render claim < 0.95"},
        headers=h,
    )
    assert rv.status_code == 201
    assert rv.json()["status"] == "pending"

    # 7. publish_report
    pub = await client.post(
        f"/v1/projects/{pid}/reports",
        json={"format": "markdown"},
        headers=h,
    )
    assert pub.status_code == 201, pub.text
    public = await client.get(f"/v1/reports/{pid}")
    assert public.status_code == 200
    body = public.json()["body"]
    assert "Confirmed" in body
    assert "Render" in body
