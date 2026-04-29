"""Events emit() writes a row and triggers pg_notify; subscribe() yields it."""

import asyncio
import json

import pytest


@pytest.mark.asyncio
async def test_emit_writes_row_and_recent_lists_it(client, agent):
    _, agent_id, key = agent
    h = {"Authorization": f"Bearer {key}"}
    p = (await client.post("/v1/projects", json={"topic": "t", "depth": "quick"}, headers=h)).json()

    r = await client.get(f"/v1/events/recent?agent_key={key}", headers=h)
    assert r.status_code == 200
    rows = r.json()
    kinds = [e["kind"] for e in rows]
    assert "start_research" in kinds


@pytest.mark.asyncio
async def test_subscribe_yields_live_events(agent, db_pool):
    """Direct service-level test: subscribe + emit → receive."""
    from margin_api.services import events as events_svc

    _, agent_id, _ = agent

    # Open an explicit listener and consume the first live event.
    received = asyncio.get_event_loop().create_future()

    async def consumer():
        async for ev in events_svc.subscribe(agent_id, since=None):
            received.set_result(ev)
            return

    task = asyncio.create_task(consumer())
    # Tiny delay so LISTEN is in place.
    await asyncio.sleep(0.2)

    async with db_pool.acquire() as conn:
        await events_svc.emit(
            conn,
            agent_id=agent_id,
            project_id=None,
            kind="ping",
            payload={"hello": "world"},
        )

    try:
        ev = await asyncio.wait_for(received, timeout=3.0)
        assert ev["kind"] == "ping"
        # payload may be JSON-decoded already
        if isinstance(ev["payload"], str):
            ev["payload"] = json.loads(ev["payload"])
        assert ev["payload"]["hello"] == "world"
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
