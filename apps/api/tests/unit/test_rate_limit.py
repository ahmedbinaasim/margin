import asyncio

import pytest

from margin_api.config import get_settings, reset_settings
from margin_api.rate_limit import check, reset


@pytest.mark.asyncio
async def test_rate_limit_allows_under_cap(monkeypatch):
    reset_settings()
    s = get_settings()
    # Tighten the cap to 3 for this test.
    monkeypatch.setattr(s, "rate_limit_per_minute", 3)
    reset()
    for _ in range(3):
        assert await check("ag_test") is True
    assert await check("ag_test") is False


@pytest.mark.asyncio
async def test_rate_limit_isolates_agents():
    reset()
    assert await check("ag_a") is True
    assert await check("ag_b") is True
