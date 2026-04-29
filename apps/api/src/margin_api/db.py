"""Asyncpg connection pool wired into FastAPI's lifespan."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import asyncpg

from .config import get_settings

_pool: asyncpg.Pool | None = None


async def init_pool(dsn: str | None = None) -> asyncpg.Pool:
    """Create the global pool. Call once at startup."""
    global _pool
    if _pool is not None:
        return _pool
    dsn = dsn or get_settings().database_url
    _pool = await asyncpg.create_pool(
        dsn,
        min_size=1,
        max_size=10,
        command_timeout=30,
        init=_init_connection,
    )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialized. Call init_pool() first.")
    return _pool


@asynccontextmanager
async def acquire() -> AsyncIterator[asyncpg.Connection]:
    async with get_pool().acquire() as conn:
        yield conn


async def _init_connection(conn: asyncpg.Connection) -> None:
    """Set up codecs for jsonb (and any future custom types).

    pgvector values are passed in/out as strings (``'[0.1,0.2,...]'``) with a
    ``::vector`` cast in the SQL — no codec needed. This avoids fighting the
    asyncpg type-codec machinery when extensions aren't loaded yet.
    """

    await conn.set_type_codec(
        "jsonb",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
        format="text",
    )


async def fetch_one(query: str, *args: Any) -> asyncpg.Record | None:
    async with acquire() as conn:
        return await conn.fetchrow(query, *args)


async def fetch_many(query: str, *args: Any) -> list[asyncpg.Record]:
    async with acquire() as conn:
        return list(await conn.fetch(query, *args))


async def execute(query: str, *args: Any) -> str:
    async with acquire() as conn:
        return await conn.execute(query, *args)
