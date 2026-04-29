"""Seed a demo owner + agent + sample project for local development.

Prints the plaintext API key once. Re-running is safe: the demo owner is
upserted by email, but a fresh agent + key is minted each run.

Usage:
    DATABASE_URL=postgresql://... python infra/seed.py
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import sys

import asyncpg
import bcrypt


DEMO_EMAIL = os.environ.get("SEED_EMAIL", "demo@margin.dev")
DEMO_AGENT_NAME = os.environ.get("SEED_AGENT_NAME", "Demo Agent")


def mint_api_key() -> str:
    return "ag_live_" + secrets.token_hex(12)


async def main() -> int:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("error: DATABASE_URL is not set", file=sys.stderr)
        return 2

    conn = await asyncpg.connect(dsn)
    try:
        owner_id = await conn.fetchval(
            """
            INSERT INTO owners (email) VALUES ($1)
            ON CONFLICT (email) DO UPDATE SET email = EXCLUDED.email
            RETURNING owner_id
            """,
            DEMO_EMAIL,
        )

        plaintext_key = mint_api_key()
        key_prefix = plaintext_key[:12]
        key_hash = bcrypt.hashpw(plaintext_key.encode(), bcrypt.gensalt()).decode()

        agent_id = await conn.fetchval(
            """
            INSERT INTO agents (owner_id, name, key_hash, key_prefix)
            VALUES ($1, $2, $3, $4)
            RETURNING agent_id
            """,
            owner_id,
            DEMO_AGENT_NAME,
            key_hash,
            key_prefix,
        )

        # One sample project + a few findings, so the dashboard isn't empty.
        project_id = await conn.fetchval(
            """
            INSERT INTO projects (agent_id, topic, depth)
            VALUES ($1, $2, 'standard')
            RETURNING project_id
            """,
            agent_id,
            "free-tier MCP hosting in 2026",
        )

        sample_findings = [
            (
                "Koyeb's free instance scales to zero after 1 hour idle, not 15 minutes.",
                "Koyeb docs: 'Free instances are paused after 1 hour without traffic.'",
                "https://www.koyeb.com/docs/pricing",
                0.95,
            ),
            (
                "Render free web services sleep after 15 minutes of inactivity.",
                "Render docs: 'Free web services spin down after 15 minutes of no traffic.'",
                "https://render.com/docs/free",
                0.9,
            ),
            (
                "Neon free tier is never paused on inactivity (vs. Supabase's 7-day pause).",
                "Neon pricing page: 'Always-on free tier — no inactivity pauses.'",
                "https://neon.tech/pricing",
                0.85,
            ),
        ]

        for claim, evidence, source, conf in sample_findings:
            content_hash = f"seed-{secrets.token_hex(4)}"
            finding_id = await conn.fetchval(
                """
                INSERT INTO findings (project_id, agent_id, claim, evidence, source_url, confidence, content_hash)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING finding_id
                """,
                project_id,
                agent_id,
                claim,
                evidence,
                source,
                conf,
                content_hash,
            )
            await conn.execute(
                """
                INSERT INTO events (agent_id, project_id, kind, payload)
                VALUES ($1, $2, 'add_finding', $3::jsonb)
                """,
                agent_id,
                project_id,
                json.dumps(
                    {"finding_id": finding_id, "claim": claim[:120], "confidence": conf}
                ),
            )

        print("--- Margin demo seed ---")
        print(f"owner_id:    {owner_id}  ({DEMO_EMAIL})")
        print(f"agent_id:    {agent_id}  ({DEMO_AGENT_NAME})")
        print(f"project_id:  {project_id}")
        print(f"API key:     {plaintext_key}")
        print()
        print("Use the key with:")
        print(f"  curl -H 'Authorization: Bearer {plaintext_key}' http://localhost:8080/v1/projects")
        print(f"  MCP URL: http://localhost:8080/mcp/{plaintext_key}")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
