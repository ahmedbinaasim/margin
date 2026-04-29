"""Asyncpg connection pool wired into FastAPI's lifespan."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

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
    """Set up codecs for jsonb and the pgvector extension."""

    await conn.set_type_codec(
        "jsonb",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
        format="text",
    )

    # pgvector: register the vector type so we can pass python lists in/out.
    try:
        await conn.execute("SELECT 1")  # cheap probe to confirm conn alive
        await _register_vector(conn)
    except Exception:
        # If pgvector isn't installed, vector cols simply use text encoding;
        # the migrations require pgvector so this should not happen in prod.
        pass


async def _register_vector(conn: asyncpg.Connection) -> None:
    """Encode vectors as pgvector strings, decode them back to python lists."""

    def _encode(v: list[float]) -> str:
        # pgvector accepts a literal like '[0.1,0.2,...]'
        return "[" + ",".join(f"{x:.7f}" for x in v) + "]"

    def _decode(s: str) -> list[float]:
        # incoming form: '[0.1,0.2,...]'
        return [float(x) for x in s[1:-1].split(",")] if s and s != "[]" else []

    try:
        await conn.set_type_codec(
            "vector",
            encoder=_encode,
            decoder=_decode,
            schema="public",
            format="text",
        )
    except asyncpg.exceptions.UndefinedObjectError:
        # pgvector not present yet (first migration); ignore.
        pass


async def fetch_one(query: str, *args: Any) -> asyncpg.Record | None:
    async with acquire() as conn:
        return await conn.fetchrow(query, *args)


async def fetch_many(query: str, *args: Any) -> list[asyncpg.Record]:
    async with acquire() as conn:
        return list(await conn.fetch(query, *args))


async def execute(query: str, *args: Any) -> str:
    async with acquire() as conn:
        return await conn.execute(query, *args)
