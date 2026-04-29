"""Smoke tests for the Margin Python SDK."""

import pytest
import respx
import httpx

from margin import AsyncMargin, Margin, MarginError


@respx.mock
def test_start_research_sync():
    respx.post("http://api.test/v1/projects").mock(
        return_value=httpx.Response(
            201,
            json={
                "project_id": "p_abc",
                "topic": "x",
                "depth": "thorough",
                "deadline": None,
                "created_at": "2026-04-30T00:00:00Z",
                "dashboard_url": "http://app/p/p_abc",
            },
        )
    )
    with Margin(api_key="ag_live_x", base_url="http://api.test") as m:
        out = m.start_research(topic="x", depth="thorough")
    assert out["project_id"] == "p_abc"


@respx.mock
def test_error_raises():
    respx.post("http://api.test/v1/projects/p_x/findings").mock(
        return_value=httpx.Response(409, json={"detail": "contradicts must reference same project"})
    )
    with Margin(api_key="ag_live_x", base_url="http://api.test") as m:
        with pytest.raises(MarginError) as ei:
            m.add_finding("p_x", claim="c", evidence="e", confidence=0.5)
    assert ei.value.status == 409


@respx.mock
@pytest.mark.asyncio
async def test_async_publish_report():
    respx.post("http://api.test/v1/projects/p_abc/reports").mock(
        return_value=httpx.Response(
            201,
            json={
                "report_id": "rp_1",
                "project_id": "p_abc",
                "format": "markdown",
                "public_slug": "p_abc",
                "report_url": "http://app/r/p_abc",
                "created_at": "2026-04-30T00:00:00Z",
            },
        )
    )
    async with AsyncMargin(api_key="ag_live_x", base_url="http://api.test") as m:
        out = await m.publish_report("p_abc")
    assert out["report_url"].endswith("/r/p_abc")
