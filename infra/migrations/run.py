"""Idempotent migration runner.

Scans `infra/migrations/*.sql` lexicographically and applies the ones that
haven't been recorded in the `_migrations` table.

Usage:
    DATABASE_URL=postgresql://... python infra/migrations/run.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import asyncpg


MIGRATIONS_DIR = Path(__file__).resolve().parent


async def main() -> int:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("error: DATABASE_URL is not set", file=sys.stderr)
        return 2

    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS _migrations (
                name        TEXT PRIMARY KEY,
                applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )

        applied = {row["name"] for row in await conn.fetch("SELECT name FROM _migrations")}

        files = sorted(p for p in MIGRATIONS_DIR.glob("*.sql"))
        if not files:
            print("no migration files found")
            return 0

        for path in files:
            name = path.name
            if name in applied:
                print(f"skip  {name}")
                continue
            print(f"apply {name}")
            sql = path.read_text()
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute("INSERT INTO _migrations (name) VALUES ($1)", name)
        print("done")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
