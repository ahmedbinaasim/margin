"""request_human_review + dashboard decide flow."""

import pytest


@pytest.mark.asyncio
async def test_request_review_moves_project_to_review_requested(client, agent):
    _, _, key = agent
    h = {"Authorization": f"Bearer {key}"}
    p = (await client.post("/v1/projects", json={"topic": "test topic", "depth": "quick"}, headers=h)).json()
    r = await client.post(
        f"/v1/projects/{p['project_id']}/reviews",
        json={"reason": "low confidence on X"},
        headers=h,
    )
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "pending"

    plist = await client.get("/v1/projects", headers=h)
    assert plist.status_code == 200
    target = [x for x in plist.json()["projects"] if x["project_id"] == p["project_id"]][0]
    assert target["status"] == "review_requested"
