"""Shared fixtures.

- ``db_pool`` — connects to TEST_DATABASE_URL (or DATABASE_URL), runs migrations
  on a fresh schema, exposes asyncpg.Pool. The schema is dropped + recreated
  per session.
- ``agent`` — seeds an owner+agent and yields the plaintext API key.
- ``client`` — httpx.AsyncClient against the in-process FastAPI app.
- ``mock_externals`` (autouse) — respx-mocks Voyage and Groq so unit tests
  never touch the network.
"""

from __future__ import annotations

import asyncio
import os
import secrets
from pathlib import Path
from typing import AsyncIterator

import bcrypt
import pytest
import pytest_asyncio
import respx
from httpx import ASGITransport, AsyncClient, Response

# Force the test database BEFORE importing margin_api so config picks it up.
TEST_DSN = os.environ.get("TEST_DATABASE_URL") or os.environ.get(
    "DATABASE_URL", "postgresql://margin:margin@localhost:5432/margin_test"
)
os.environ["DATABASE_URL"] = TEST_DSN
os.environ.setdefault("VOYAGE_API_KEY", "test-voyage-key")
os.environ.setdefault("GROQ_API_KEY", "")  # ensure Groq stays disabled in tests

from margin_api import db as db_mod  # noqa: E402
from margin_api.auth import clear_cache as clear_auth_cache  # noqa: E402
from margin_api.config import reset_settings  # noqa: E402
from margin_api.embeddings import clear_cache as clear_embed_cache  # noqa: E402
from margin_api.main import create_app  # noqa: E402
from margin_api.rate_limit import reset as reset_rate_limit  # noqa: E402

MIGRATION_SQL = (
    Path(__file__).resolve().parents[3] / "infra" / "migrations" / "001_init.sql"
).read_text()


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def _migrated_db():
    """Apply migrations once per session into TEST_DSN."""
    import asyncpg

    conn = await asyncpg.connect(TEST_DSN)
    try:
        # Wipe public schema for a clean slate.
        await conn.execute("DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;")
        await conn.execute(MIGRATION_SQL)
    finally:
        await conn.close()
    yield


@pytest_asyncio.fixture
async def db_pool(_migrated_db):
    reset_settings()
    pool = await db_mod.init_pool(TEST_DSN)
    # Truncate per test for isolation (skip _migrations).
    async with pool.acquire() as conn:
        await conn.execute(
            """
            TRUNCATE
                events, citations, findings, reviews, reports,
                projects, agents, auth_codes, owners
            RESTART IDENTITY CASCADE
            """
        )
    clear_auth_cache()
    clear_embed_cache()
    reset_rate_limit()
    yield pool
    await db_mod.close_pool()


@pytest_asyncio.fixture
async def agent(db_pool) -> tuple[str, str, str]:
    """Returns (owner_id, agent_id, plaintext_key)."""
    plaintext = "ag_live_" + secrets.token_hex(12)
    key_hash = bcrypt.hashpw(plaintext.encode(), bcrypt.gensalt(rounds=4)).decode()
    async with db_pool.acquire() as conn:
        owner_id = await conn.fetchval(
            "INSERT INTO owners (email) VALUES ($1) RETURNING owner_id",
            "test@margin.dev",
        )
        agent_id = await conn.fetchval(
            """
            INSERT INTO agents (owner_id, name, key_hash, key_prefix)
            VALUES ($1, $2, $3, $4)
            RETURNING agent_id
            """,
            owner_id,
            "Test Agent",
            key_hash,
            plaintext[:12],
        )
    return owner_id, agent_id, plaintext


@pytest_asyncio.fixture
async def client(db_pool) -> AsyncIterator[AsyncClient]:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


# --- Mocks for external HTTP services (Voyage, Groq) ---


@pytest.fixture(autouse=True)
def mock_externals(request):
    """Mock Voyage embeddings and Groq calls so unit/integration tests don't touch the net.

    Tests that explicitly want live external calls can opt out with ``@pytest.mark.live``.
    Tests that want to use the local sentence-transformers fallback can opt in with
    ``@pytest.mark.local_embed``.
    """

    if "live" in request.keywords:
        yield
        return

    with respx.mock(assert_all_called=False) as m:
        # Voyage embed: return a deterministic 1024-dim vector keyed off text length.
        def _voyage_response(req):
            import json

            body = json.loads(req.content)
            texts = body.get("texts") or body.get("input") or []
            if isinstance(texts, str):
                texts = [texts]
            data = []
            for i, t in enumerate(texts):
                # Deterministic-ish: first dim == length, then ramp.
                vec = [float(len(t)) % 7.0, float(i) % 5.0] + [0.01 * (k + 1) for k in range(1022)]
                data.append(vec)
            return Response(
                200,
                json={
                    "object": "list",
                    "data": [{"embedding": v, "index": i} for i, v in enumerate(data)],
                    "model": "voyage-3.5-lite",
                    "usage": {"total_tokens": sum(len(t) for t in texts)},
                    # voyageai SDK expects this shape — see voyageai source
                    "embeddings": data,
                },
            )

        m.post("https://api.voyageai.com/v1/embeddings").mock(side_effect=_voyage_response)

        # Groq is gated by api_key in our llm.py; it shouldn't be called when the
        # key is empty, but mock to be safe.
        m.post("https://api.groq.com/openai/v1/chat/completions").mock(
            return_value=Response(
                200,
                json={
                    "id": "fake",
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": "## Overview\n\nA short test intro.",
                            },
                            "finish_reason": "stop",
                        }
                    ],
                },
            )
        )
        yield
