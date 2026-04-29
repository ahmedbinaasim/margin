"""Citation insert on success and failure paths."""

import httpx
import pytest
import respx


@pytest.mark.asyncio
@respx.mock(assert_all_called=False)
async def test_cite_inserts_row_on_fetch_success(respx_mock, client, agent):
    _, _, key = agent
    h = {"Authorization": f"Bearer {key}"}
    p = (await client.post("/v1/projects", json={"topic": "test topic", "depth": "quick"}, headers=h)).json()
    f = (
        await client.post(
            f"/v1/projects/{p['project_id']}/findings",
            json={"claim": "claim text", "evidence": "evidence", "confidence": 0.8},
            headers=h,
        )
    ).json()

    respx_mock.get("https://example.com/article").mock(
        return_value=httpx.Response(
            200,
            content=b"<html><body><h1>Headline</h1><p>Body text body text body text body text.</p></body></html>",
            headers={"content-type": "text/html"},
        )
    )

    r = await client.post(
        f"/v1/findings/{f['finding_id']}/citations",
        json={"url": "https://example.com/article", "excerpt": "Headline"},
        headers=h,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["citation_id"].startswith("c_")
    assert body["fetch_status"] == 200


@pytest.mark.asyncio
@respx.mock(assert_all_called=False)
async def test_cite_records_row_even_when_fetch_fails(respx_mock, client, agent):
    _, _, key = agent
    h = {"Authorization": f"Bearer {key}"}
    p = (await client.post("/v1/projects", json={"topic": "test topic", "depth": "quick"}, headers=h)).json()
    f = (
        await client.post(
            f"/v1/projects/{p['project_id']}/findings",
            json={"claim": "claim text", "evidence": "evidence", "confidence": 0.8},
            headers=h,
        )
    ).json()

    # Network error on fetch
    respx_mock.get("https://broken.example/").mock(side_effect=httpx.ConnectError("boom"))

    r = await client.post(
        f"/v1/findings/{f['finding_id']}/citations",
        json={"url": "https://broken.example/", "excerpt": "we tried"},
        headers=h,
    )
    assert r.status_code == 201
    body = r.json()
    assert body["fetch_status"] == 0
    assert body["archive_url"] is None  # R2 disabled in tests


@pytest.mark.asyncio
@respx.mock(assert_all_called=False)
async def test_cite_idempotent_on_finding_and_pagehash(respx_mock, client, agent):
    _, _, key = agent
    h = {"Authorization": f"Bearer {key}"}
    p = (await client.post("/v1/projects", json={"topic": "test topic", "depth": "quick"}, headers=h)).json()
    f = (
        await client.post(
            f"/v1/projects/{p['project_id']}/findings",
            json={"claim": "claim text", "evidence": "evidence", "confidence": 0.8},
            headers=h,
        )
    ).json()

    respx_mock.get("https://example.com/dup").mock(
        return_value=httpx.Response(
            200,
            content=b"<html><body><p>same content same content same content</p></body></html>",
        )
    )

    r1 = await client.post(
        f"/v1/findings/{f['finding_id']}/citations",
        json={"url": "https://example.com/dup", "excerpt": "first"},
        headers=h,
    )
    r2 = await client.post(
        f"/v1/findings/{f['finding_id']}/citations",
        json={"url": "https://example.com/dup", "excerpt": "second"},
        headers=h,
    )
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["citation_id"] == r2.json()["citation_id"]
