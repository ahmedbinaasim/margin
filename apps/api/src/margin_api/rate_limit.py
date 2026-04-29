"""Tiny in-process leaky-bucket rate limiter, keyed by agent_id.

Good enough for a free-tier MVP. Replace with a Redis token bucket once
multi-instance scaling is needed.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from typing import Deque, Dict

from .config import get_settings


_buckets: Dict[str, Deque[float]] = defaultdict(deque)
_lock = asyncio.Lock()
_WINDOW_SEC = 60.0


async def check(agent_id: str) -> bool:
    """Return True if the call is allowed; False if over budget for the window."""
    settings = get_settings()
    cap = settings.rate_limit_per_minute
    now = time.monotonic()
    cutoff = now - _WINDOW_SEC
    async with _lock:
        bucket = _buckets[agent_id]
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= cap:
            return False
        bucket.append(now)
    return True


def reset() -> None:
    _buckets.clear()
