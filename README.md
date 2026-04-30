# Margin

**The research workspace for AI agents.** Eight primitives. MCP + REST. Free tier.

> Memory tools store facts. Browsers give agents bodies. Sandboxes give them hands.
> Margin is the **workspace** — the durable, structured, citation-backed artifact
> the agent produces and hands off across sessions, models, and human reviewers.

See [`SPEC.md`](./SPEC.md) for the full design (data model, deployment plan,
demo script, and YC application copy).

---

## Quickstart in 60 seconds

1. **Get a key.** Visit `https://margin.dev/app`, sign in with email, mint an
   agent. Copy the plaintext key — it's shown once.

2. **Add to Claude.** Paste this into Claude.ai → Settings → Connectors:
   ```
   https://api.margin.dev/mcp/<your-key>
   ```
   All eight tools appear as soon as the connector saves.

3. **Or call REST.**
   ```bash
   curl -X POST https://api.margin.dev/v1/projects \
     -H "Authorization: Bearer $MARGIN_KEY" \
     -d '{"topic":"free-tier MCP hosting","depth":"thorough"}'
   # → { "project_id": "p_K1aZ9b...", "dashboard_url": "..." }
   ```

---

## The eight primitives

| Tool | Purpose |
|---|---|
| `start_research(topic, depth?, deadline?)` | Begin a research project. |
| `add_finding(project_id, claim, evidence, confidence, source?, contradicts?)` | Record a typed claim with evidence. Idempotent on (project, hash). |
| `cite(finding_id, url, excerpt)` | Attach a citation; we fetch, extract, hash, archive. |
| `query_findings(project_id, semantic_query, limit?, min_confidence?)` | Semantic recall over prior findings via Voyage embeddings. |
| `branch_project(project_id, reason)` | Fork into a sub-investigation; parent stays intact. |
| `request_human_review(project_id, reason)` | Pause for human approval. Surfaces on the dashboard. |
| `publish_report(project_id, format?)` | Render a citation-backed report at a stable public URL. |
| `list_projects(limit?, status?)` | List the calling agent's projects, most recent first. |

Each tool is exposed twice — once as an MCP tool over Streamable HTTP, once
as a REST endpoint. Same business logic behind both.

---

## Why Margin

The agent-infra layer below us is funded — Mem0 raised $24M for memory, Zep
similar, Browserbase Series B at $300M, Composio $29M. But **the research
workspace category is empty.** NotebookLM and Claude Projects are clients
for humans. Memory tools store facts, not artifacts. Skills are procedural,
not persistent. Margin sells the artifact, not the memory.

Built for [Aaron Epstein's "Software for Agents" RFS](https://www.ycombinator.com/rfs).
The lane is open.

---

## Self-host on Render (free tier)

1. Fork this repo.
2. Sign up at https://render.com (no credit card required).
3. New → Blueprint → connect this repo. Render reads `render.yaml` automatically.
4. When prompted, paste secret values for: `DATABASE_URL` (Neon), `JWT_SECRET` (generate with `openssl rand -hex 32`), `VOYAGE_API_KEY`, `GROQ_API_KEY`, `R2_*`, `RESEND_API_KEY`.
5. After first deploy, visit `https://<your-service>.onrender.com/healthz` to confirm.
6. Optional: add a custom domain (`api.<yourdomain>`) under Render → Settings → Custom Domains.
7. The included GitHub Actions workflow at `.github/workflows/keepalive.yml` will ping the service every 10 minutes to prevent sleep. Enable Actions on your fork.

### Local dev

```bash
# 1. Postgres + pgvector (Neon free tier works; for local dev:)
docker compose up -d postgres

# 2. Apply migrations
DATABASE_URL=postgresql://margin:margin@localhost:5432/margin python infra/migrations/run.py

# 3. Seed a demo agent
DATABASE_URL=... python infra/seed.py     # prints an API key once

# 4. Run the API
cd apps/api
uv sync --all-extras
uv run uvicorn margin_api.main:app --reload --port 8080

# 5. Run the dashboard
cd apps/web
npm install && npm run dev               # → http://localhost:3000
```

Or in one container:

```bash
docker run -p 8080:8080 \
  -e DATABASE_URL=... -e VOYAGE_API_KEY=... -e GROQ_API_KEY=... \
  ghcr.io/ahmedbinaasim/margin-api:latest
```

---

## Stack

| Slot | Choice |
|---|---|
| Backend compute | Render free web service (with GitHub Actions keep-alive ping) |
| Frontend | Cloudflare Pages (static export) |
| Postgres + vectors | Neon free (always-on) + pgvector |
| Blob storage | Cloudflare R2 (zero egress) |
| Embeddings | **Voyage 3.5-lite** @ 1024d → truncated to 768d → L2-renormalized |
| Embedding fallback | Local `BAAI/bge-small-en-v1.5` (zero-padded 384→768) |
| LLM | Groq llama-3.3-70b-versatile (report TOC) |
| Web extraction | httpx + trafilatura |

Cost basis: **$0/mo** recurring (optional $11/yr for `.dev` domain).

---

## Tests

```bash
# API: unit + integration + e2e (against a local Postgres+pgvector)
cd apps/api && uv run pytest -q

# SDK
cd packages/sdk-py && pytest -q

# Frontend (Playwright; needs the api + dev server running)
cd apps/web && MARGIN_API_RUNNING=1 npm run test
```

CI runs all of the above on every push (`.github/workflows/ci.yml`).

---

## Repo layout

```
margin/
├── apps/api/             # FastAPI + FastMCP (Python 3.12, uv)
├── apps/web/             # Next.js 15 App Router, static export
├── packages/sdk-py/      # Python SDK
├── infra/                # migrations, seed
├── docs/                 # landing copy, YC app draft, demo script
├── SPEC.md               # full design doc
└── .github/workflows/    # CI
```

MIT licensed. PRs welcome.
