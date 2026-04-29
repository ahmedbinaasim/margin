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


def _fake_embed_text(text: str, dim: int = 1024) -> list[float]:
    """Deterministic 1024-d vector seeded by sha256(text). Test-only."""
    import hashlib

    h = hashlib.sha256(text.encode()).digest()
    # Stretch the 32-byte hash into `dim` floats in (-1, 1).
    out: list[float] = []
    seed = list(h)
    for i in range(dim):
        b = seed[i % 32] ^ (i & 0xFF)
        # Map 0-255 to -1..1
        out.append((b - 128) / 128.0)
    return out


@pytest.fixture(autouse=True)
def mock_externals(request, monkeypatch):
    """Stub external SDKs so tests are hermetic.

    voyageai uses aiohttp under the hood (not httpx), so respx wouldn't intercept
    it cleanly. Instead, we monkeypatch ``_embed_voyage`` to return deterministic
    vectors. The truncate + L2-normalize logic in ``embed()`` still runs, so we
    exercise the real production path everywhere except the network boundary.

    Tests that explicitly want live external calls can opt out with
    ``@pytest.mark.live``.
    """

    if "live" in request.keywords:
        yield
        return

    from margin_api import embeddings as em

    async def _stub_voyage(texts, input_type):
        from margin_api.config import get_settings

        s = get_settings()
        return [
            em._truncate_and_renormalize(_fake_embed_text(t), s.embed_dim) for t in texts
        ]

    monkeypatch.setattr(em, "_embed_voyage", _stub_voyage)

    # Groq is gated on api_key being set; we leave it empty in tests, so it's
    # never invoked. No mock needed.
    yield
