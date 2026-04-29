# Margin: an agent-native research workspace — full build spec

**One-page executive summary**

**Margin is a hosted research workspace whose primary user is an AI agent.** Agents connect over MCP (Streamable HTTP) or REST, call eight primitives — `start_research`, `add_finding`, `cite`, `query_findings`, `branch_project`, `request_human_review`, `publish_report`, `list_projects` — and Margin gives them durable, typed, citation-backed state that survives sessions, models, and handoffs. The agent does the actual research (browsing, reasoning, writing); Margin owns the persistent ledger.

**Why now.** Aaron Epstein's Summer 2026 RFS says explicitly that agents need _"APIs, MCPs, and CLIs"_ with _"thorough documentation"_ and that _"every major category of software that people use today needs to be rebuilt for agents."_ Memory (Mem0, Zep, Letta), browsers (Browserbase), and sandboxes (E2B) are funded; **the agent-native research workspace is an empty category** in April 2026. Skills are procedural and don't persist artifacts. Mem0/Zep store facts, not structured documents. The lane is open.

**What we ship in 2 days.** A live `https://margin.<chosen-tld>` landing page with copyable MCP install command, a Next.js dashboard at `/app` rendering an agent activity timeline, and a Python FastAPI + FastMCP service exposing eight tools and a REST mirror, backed by Neon Postgres + pgvector and Cloudflare R2. End-to-end demo: Claude Desktop user adds Margin via a single URL, runs a literature review, closes the chat, opens a new chat the next day, queries findings semantically, branches to investigate a contradiction, requests human review, publishes a markdown report.

**Cost.** $0 recurring, optionally $0.99 for a `.xyz` domain. Stack: Koyeb (FastAPI), Cloudflare Pages (Next.js), Neon (Postgres + pgvector), Cloudflare R2 (raw HTML), GitHub Actions (CI), Voyage 3.5-lite @ 768d (embeddings, with local `bge-small-en-v1.5` fallback), Groq llama-3.3-70b (LLM).

**Deliverable.** Live URL, public GitHub repo, a 60-second founders' video for the YC form, and a 90-second screen recording of Claude using Margin end-to-end.

---

## 1. The user story, end to end

A solo developer named Sara is using Claude Desktop. She visits `margin.dev`, copies the single-line install (`Add to Claude → https://api.margin.dev/mcp/ag_live_aB12...`), pastes it into Claude.ai → Settings → Connectors. Claude immediately sees eight Margin tools.

Sara types: _"Research the state of free-tier MCP hosting in April 2026 and remember everything you learn."_ Claude calls `start_research(topic="free-tier MCP hosting", depth="thorough", deadline=null)` and gets `project_id=p_K1aZ9...`. It browses with its own web tools, then calls `add_finding(project_id, claim="Render free web tier sleeps after 15 min", evidence="<quote>", source="https://render.com/...", confidence=0.9)` ten to fifteen times. For each, it follows up with `cite(finding_id, url, excerpt)`. Margin fetches each URL server-side via trafilatura, hashes the cleaned markdown, stores raw HTML in R2, and embeds the claim+evidence with Voyage 3.5-lite (truncated to 768 dimensions, L2-renormalized) into pgvector.

Sara closes the chat and goes to bed. The next morning she opens a fresh Claude conversation and says _"continue the MCP hosting research and look for contradictions."_ Claude calls `list_projects(agent_id)`, gets `p_K1aZ9` back with a summary, then `query_findings(project_id, semantic_query="cold start times")` and gets the prior findings ranked by cosine similarity. It identifies a contradiction (one source says Koyeb cold-starts in seconds, another in milliseconds), calls `branch_project(project_id, reason="contradicting cold-start claims")` to fork a sub-investigation, and resolves it. It then calls `request_human_review(project_id, reason="confidence on hosted-MCP-on-Render claim < 0.7")`. Sara gets a notification on the `/app` dashboard, opens it, sees the agent's reasoning trace and the live timeline, approves. Claude calls `publish_report(project_id, format="markdown")` and returns a stable URL like `https://margin.dev/r/p_K1aZ9` that Sara shares on Twitter.

Throughout, the `/app` dashboard shows a live SSE stream: _"ag_sara → add_finding → p_K1aZ9 → 'Render free web tier sleeps...' (0.9 conf)"_ in real time.

---

## 2. Final-state description: what's deployed at the end of 2 days

**One Git repository** (`github.com/<you>/margin`, public, MIT) containing:

- `apps/api/` — Python 3.12 FastAPI + FastMCP service, deployed to Koyeb, reachable at `https://margin-api-<id>.koyeb.app`. CNAMEd to `api.margin.<tld>`.
- `apps/web/` — Next.js 15 (App Router) static-export marketing site + dashboard, deployed to Cloudflare Pages, reachable at `https://margin.<tld>`.
- `packages/sdk-py/` — a 200-line Python client (optional polish).
- `infra/` — `koyeb.yaml`, GitHub Actions workflow, SQL migrations.
- `README.md` — landing-page-style with copyable curl + Claude install snippet.
- `SPEC.md` — this document.

**Live surfaces:**

| Surface              | URL                                | Purpose                                                                                                |
| -------------------- | ---------------------------------- | ------------------------------------------------------------------------------------------------------ |
| Landing              | `margin.<tld>/`                    | One-sentence hero, copy-paste MCP install, embedded demo video, 5-line curl.                           |
| Dashboard            | `margin.<tld>/app`                 | Sign in (passwordless email link via own JWT), view agents, mint API keys, see live activity timeline. |
| Public report viewer | `margin.<tld>/r/<project_id>`      | Renders published reports (markdown → HTML, served as static-ish Next.js).                             |
| MCP endpoint         | `api.margin.<tld>/mcp/<api_key>`   | Streamable HTTP MCP server.                                                                            |
| REST mirror          | `api.margin.<tld>/v1/*`            | All eight primitives also exposed as `POST`endpoints with `Bearer`auth.                                |
| OpenAPI              | `api.margin.<tld>/v1/openapi.json` | Auto-generated by FastAPI.                                                                             |
| Docs                 | `margin.<tld>/docs`                | Static Next.js page rendering the OpenAPI + MCP tool reference.                                        |

**Demo asset:** a 90-second screen recording (`demo.mp4`) committed to the repo and embedded on the landing page.

---

## 3. Data model — full SQL DDL

Postgres 16 on Neon. One database, one schema (`public`). Vectors via `pgvector`. Generated IDs are short, prefixed, URL-safe.

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Owners are humans. One owner, many agents (each with its own API key).
CREATE TABLE owners (
    owner_id    TEXT PRIMARY KEY DEFAULT ('o_' || encode(gen_random_bytes(8), 'hex')),
    email       CITEXT UNIQUE NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- An "agent" is an API-key-bearing principal. The same human can have many.
CREATE TABLE agents (
    agent_id    TEXT PRIMARY KEY DEFAULT ('ag_' || encode(gen_random_bytes(10), 'hex')),
    owner_id    TEXT NOT NULL REFERENCES owners(owner_id) ON DELETE CASCADE,
    name        TEXT NOT NULL,                              -- "Sara's Claude Desktop"
    key_hash    TEXT NOT NULL,                              -- bcrypt of the plaintext key
    key_prefix  TEXT NOT NULL,                              -- first 12 chars, for UI display
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at TIMESTAMPTZ
);
CREATE INDEX idx_agents_owner ON agents(owner_id);
CREATE INDEX idx_agents_prefix ON agents(key_prefix);

-- A research project, owned by exactly one agent.
CREATE TABLE projects (
    project_id   TEXT PRIMARY KEY DEFAULT ('p_' || encode(gen_random_bytes(8), 'hex')),
    agent_id     TEXT NOT NULL REFERENCES agents(agent_id) ON DELETE CASCADE,
    topic        TEXT NOT NULL,
    depth        TEXT NOT NULL CHECK (depth IN ('quick','standard','thorough')),
    deadline     TIMESTAMPTZ,
    parent_id    TEXT REFERENCES projects(project_id),     -- for branches
    branch_reason TEXT,
    status       TEXT NOT NULL DEFAULT 'active'
                 CHECK (status IN ('active','review_requested','published','archived')),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_projects_agent ON projects(agent_id, updated_at DESC);
CREATE INDEX idx_projects_parent ON projects(parent_id);

-- A typed finding: claim + evidence + source + confidence.
CREATE TABLE findings (
    finding_id      TEXT PRIMARY KEY DEFAULT ('f_' || encode(gen_random_bytes(8), 'hex')),
    project_id      TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    agent_id        TEXT NOT NULL REFERENCES agents(agent_id),
    claim           TEXT NOT NULL,
    evidence        TEXT NOT NULL,
    source_url      TEXT,
    confidence      REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    contradicts     TEXT REFERENCES findings(finding_id),  -- optional pointer
    embedding       VECTOR(768),                            -- voyage-3.5-lite 1024d → truncated to 768d → L2-renormalized
    content_hash    TEXT NOT NULL,                          -- sha256 of claim||evidence
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_findings_project ON findings(project_id, created_at DESC);
CREATE INDEX idx_findings_hash ON findings(content_hash);
CREATE INDEX idx_findings_contradicts ON findings(contradicts);
-- HNSW for semantic recall; lists is auto-tuned by pgvector 0.8+.
CREATE INDEX idx_findings_embedding ON findings USING hnsw (embedding vector_cosine_ops);

-- Citations are immutable evidence rows pointing at cached source HTML.
CREATE TABLE citations (
    citation_id   TEXT PRIMARY KEY DEFAULT ('c_' || encode(gen_random_bytes(8), 'hex')),
    finding_id    TEXT NOT NULL REFERENCES findings(finding_id) ON DELETE CASCADE,
    url           TEXT NOT NULL,
    canonical_url TEXT NOT NULL,        -- normalized (lowercase host, no utm, no fragment)
    excerpt       TEXT NOT NULL,
    page_hash     TEXT NOT NULL,        -- sha256 of cleaned markdown
    r2_key        TEXT,                 -- S3 key in R2 bucket; null if fetch failed
    fetched_at    TIMESTAMPTZ,
    fetch_status  INT,                  -- HTTP status, or 0 for failure
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_citations_finding ON citations(finding_id);
CREATE INDEX idx_citations_pagehash ON citations(page_hash);

-- Human review requests.
CREATE TABLE reviews (
    review_id     TEXT PRIMARY KEY DEFAULT ('rv_' || encode(gen_random_bytes(8), 'hex')),
    project_id    TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    reason        TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending','approved','rejected')),
    decided_at    TIMESTAMPTZ,
    decided_note  TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_reviews_project ON reviews(project_id);

-- Published reports.
CREATE TABLE reports (
    report_id    TEXT PRIMARY KEY DEFAULT ('rp_' || encode(gen_random_bytes(8), 'hex')),
    project_id   TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    format       TEXT NOT NULL CHECK (format IN ('markdown','html','json')),
    body         TEXT NOT NULL,           -- the rendered report
    public_slug  TEXT UNIQUE NOT NULL,    -- short URL slug, defaults to project_id
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_reports_slug ON reports(public_slug);

-- Append-only event log; powers the dashboard's live timeline via SSE.
CREATE TABLE events (
    event_id   BIGSERIAL PRIMARY KEY,
    agent_id   TEXT NOT NULL REFERENCES agents(agent_id),
    project_id TEXT REFERENCES projects(project_id) ON DELETE CASCADE,
    kind       TEXT NOT NULL,            -- 'start_research' | 'add_finding' | ...
    payload    JSONB NOT NULL,           -- a small summary, never the full evidence
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_events_agent_time ON events(agent_id, event_id DESC);
CREATE INDEX idx_events_project_time ON events(project_id, event_id DESC);
```

Row-count budget against Neon's 0.5 GB project storage: 100k findings × ~3 KB embedding + ~2 KB row = ~500 MB. Fine for the MVP; archive `events` older than 30 days if needed.

---

## 4. API surface — every endpoint and tool

Two surfaces, **same business logic** behind both. The MCP layer is a thin wrapper over the REST handlers; both call the same `services/*.py` modules.

Convention: REST under `/v1/*` with `Authorization: Bearer <api_key>`; MCP under `/mcp/<api_key>` with the key embedded in the URL (because Claude.ai's connector UI does not let users set headers — confirmed in the MCP research). The same key works for both.

### 4.1 MCP tools (eight)

Every tool returns a `structuredContent` JSON object **and** a one-line human-readable `text` block, per Anthropic's writing-tools-for-agents guidance.

#### `start_research(topic, depth, deadline?) → project_id`

> Begin a new research project. Use this when an agent is starting a substantive investigation that should persist across turns or sessions. Do NOT use for one-off questions answerable in a single search.

**Input schema:**

- `topic` (str, 4–500 chars, required) — the question or thesis.
- `depth` (enum `"quick"|"standard"|"thorough"`, default `"standard"`) — controls how aggressively the agent should pursue contradictions and breadth.
- `deadline` (ISO 8601 string, optional) — soft deadline; surfaced on the dashboard.

**Output:** `{ project_id, topic, depth, deadline, created_at, dashboard_url }`.

**Errors:** `400` invalid depth/deadline, `401` bad key, `429` quota.

**Example call (MCP JSON-RPC):** `{"name":"start_research","arguments":{"topic":"free-tier MCP hosting in 2026","depth":"thorough"}}` → `{ "project_id":"p_K1aZ9b...", "dashboard_url":"https://margin.dev/app/p/p_K1aZ9b..." }`.

#### `add_finding(project_id, claim, evidence, source?, confidence, contradicts?) → finding_id`

> Record one factual claim with its supporting evidence in a project. One claim per call; loop in the agent for multiple.

**Input:** `project_id` (str), `claim` (str, 4–500), `evidence` (str, 4–4000), `source` (URL, optional but strongly recommended), `confidence` (float 0–1, required), `contradicts` (finding_id, optional).

**Server side, on call:**

1. Compute `content_hash = sha256(normalize(claim||evidence))`.
2. If a finding with the same `content_hash` already exists in this `project_id`, return the existing `finding_id` (idempotent).
3. Otherwise: embed `claim + " " + evidence` via Voyage 3.5-lite (truncated to 768d, L2-renormalized; falls back to local `bge-small-en-v1.5` on Voyage error), INSERT into `findings`, write an `events` row, return `finding_id`.

**Output:** `{ finding_id, project_id, created_at, deduped: bool, resource_uri: "findings://<project_id>/<finding_id>" }`.

**Errors:** `400` bad project, `401`, `409` if `contradicts` not in same project. Voyage failures auto-fall-back to the local model — never surface 429 to the agent.

#### `cite(finding_id, url, excerpt) → citation_id`

> Attach a citation to a finding. The server fetches the URL, extracts the main content, hashes it, and stores the raw HTML in blob storage for provenance. Idempotent on (finding_id, page_hash).

**Server side:** GET url with `httpx` (15 s timeout, follow redirects), extract markdown via `trafilatura.extract(html, output_format="markdown")`, hash the cleaned markdown, upload raw HTML to R2 keyed by `pages/<page_hash>.html`, INSERT `citations` row.

**Output:** `{ citation_id, finding_id, page_hash, fetched_at, fetch_status, archive_url? }`. `archive_url` is a signed R2 URL valid for 7 days when the report is published.

**Errors:** `400` malformed URL, `502` if fetch fails (still inserts a citation row with `fetch_status=0` so the trail isn't lost).

#### `query_findings(project_id, semantic_query, limit?=10, min_confidence?=0.0) → findings[]`

> Semantic search over a project's findings. Use this to recall what has already been discovered before adding redundant findings.

**Server side:** embed `semantic_query` via Voyage with `input_type="query"` (query-time hint specializes the representation; documents were embedded with `input_type="document"`), run `SELECT ... ORDER BY embedding <=> :q LIMIT :limit` against pgvector. Filter by `confidence >= min_confidence`. Return `{finding_id, claim, evidence_excerpt, source_url, confidence, similarity}` for each.

**Output:** `{ project_id, query, results: [...], total }`.

#### `branch_project(project_id, reason) → new_project_id`

> Fork a project into a child investigation while keeping the parent intact. Use when you want to chase a contradiction or a sub-thread without polluting the main project.

**Server side:** INSERT a new `projects` row with `parent_id = project_id` and the same `agent_id`. Optionally copy the latest N findings via `INSERT ... SELECT` into the new project (we won't, by default — branches start clean and reference the parent through the FK).

#### `request_human_review(project_id, reason) → review_id`

> Pause and ask a human to review the project. The dashboard surfaces the request and emails the owner.

**Server side:** UPDATE `projects.status = 'review_requested'`, INSERT `reviews` row, emit `event`. Dashboard's SSE stream pushes a banner.

#### `publish_report(project_id, format?="markdown") → report_url`

> Render a structured report from the project's findings and publish it at a stable public URL.

**Server side, naive renderer (good enough for day 2):**

1. Pull all `findings` ordered by created_at.
2. Group by `confidence > 0.7` (Confirmed) vs lower (Tentative).
3. For each, render `### <claim>\n\n<evidence>\n\n[source](<source_url>) · cited <date>`.
4. If we have time, send the bullets to Groq `llama-3.3-70b-versatile` with a 200-token system prompt to produce a TOC + intro paragraph, prepended. On any LLM error, ship the naive markdown.
5. Write to `reports`, return `https://margin.<tld>/r/<public_slug>`.

#### `list_projects(agent_id?, limit?=20, status?) → projects[]`

> List the calling agent's projects, most-recent first. Note: `agent_id` is ignored if present (kept in signature for clarity); the auth context determines scope.

**Output:** `[{ project_id, topic, depth, status, num_findings, updated_at }]`.

### 4.2 REST mirror

Identical inputs and outputs, with `agent_id` always derived from the bearer token. JSON in, JSON out. FastAPI auto-generates the OpenAPI spec at `/v1/openapi.json`.

```
POST   /v1/projects                       → start_research
POST   /v1/projects/{id}/findings         → add_finding
POST   /v1/findings/{id}/citations        → cite
POST   /v1/projects/{id}/query            → query_findings
POST   /v1/projects/{id}/branches         → branch_project
POST   /v1/projects/{id}/reviews          → request_human_review
POST   /v1/projects/{id}/reports          → publish_report
GET    /v1/projects                       → list_projects
GET    /v1/events?agent_id=...&since=...  → SSE stream for the dashboard
GET    /healthz                           → liveness
```

---

## 5. Codebase file/folder structure

```
margin/
├── README.md                  # landing-page copy + curl/MCP install
├── SPEC.md                    # this document
├── LICENSE                    # MIT
├── .github/workflows/ci.yml   # lint + test + deploy
├── infra/
│   ├── koyeb.yaml             # Koyeb deployment config
│   ├── migrations/
│   │   └── 001_init.sql       # full DDL from §3
│   └── seed.py                # creates demo owner+agent, 5 findings
├── apps/
│   ├── api/
│   │   ├── pyproject.toml     # uv-managed
│   │   ├── Dockerfile         # python:3.12-slim
│   │   ├── src/margin_api/
│   │   │   ├── __init__.py
│   │   │   ├── main.py        # FastAPI app + FastMCP mount + CORS
│   │   │   ├── config.py      # Pydantic Settings; env vars
│   │   │   ├── db.py          # asyncpg pool + helpers
│   │   │   ├── auth.py        # API key middleware (FastAPI Depends + FastMCP middleware)
│   │   │   ├── models.py      # Pydantic I/O models for all 8 tools
│   │   │   ├── services/
│   │   │   │   ├── projects.py
│   │   │   │   ├── findings.py
│   │   │   │   ├── citations.py    # trafilatura + R2 upload
│   │   │   │   ├── reviews.py
│   │   │   │   ├── reports.py      # markdown rendering
│   │   │   │   └── events.py       # SSE pub/sub via Postgres LISTEN/NOTIFY
│   │   │   ├── embeddings.py  # Voyage primary, local bge-small fallback
│   │   │   ├── llm.py         # Groq only (no fallback; degrade to naive markdown)
│   │   │   ├── storage.py     # R2 boto3 client
│   │   │   ├── routes_rest.py # /v1/* endpoints
│   │   │   └── mcp_server.py  # FastMCP registration of 8 tools
│   │   └── tests/
│   │       ├── test_findings.py
│   │       ├── test_dedup.py
│   │       └── test_mcp_smoke.py
│   └── web/
│       ├── package.json       # Next.js 15, App Router
│       ├── next.config.ts     # output: 'export' for Cloudflare Pages
│       ├── app/
│       │   ├── page.tsx       # landing
│       │   ├── docs/page.tsx  # auto-rendered tool reference
│       │   ├── app/page.tsx   # dashboard (after sign-in)
│       │   ├── app/p/[id]/page.tsx
│       │   ├── r/[slug]/page.tsx   # public report viewer
│       │   └── api/
│       │       └── (none — frontend is fully static; talks to api.margin.<tld>)
│       ├── components/
│       │   ├── Hero.tsx
│       │   ├── McpInstall.tsx       # one-click copy of the connector URL
│       │   ├── ActivityTimeline.tsx # SSE-driven
│       │   └── CodeBlock.tsx
│       └── lib/api.ts
└── packages/
    └── sdk-py/
        ├── pyproject.toml
        └── margin/__init__.py    # 200-line typed client
```

---

## 6. Step-by-step implementation plan: four half-days

Each block lists the work, files touched, and binary acceptance criteria. Treat every checkbox as a hard gate.

### Day 1, morning (4 h) — backend bones and auth

**Goals.** FastAPI + FastMCP boots. Postgres schema is migrated on Neon. API-key auth works on both transports. `start_research` and `list_projects` ship end-to-end.

**Tasks.**

1. `uv init` the api project with deps: `fastapi`, `uvicorn[standard]`, `fastmcp<3`, `asyncpg`, `pydantic>=2`, `bcrypt`, `httpx`, `trafilatura`, `boto3`, `google-genai`, `groq`, `python-dotenv`, `pytest`, `pytest-asyncio`.
2. Create Neon project (free tier), copy connection string. Run `infra/migrations/001_init.sql` via `psql`. Run `infra/seed.py` to create one demo owner + agent + key, print the key.
3. Implement `config.py` with `Settings(BaseSettings)` reading env vars (see §8).
4. Implement `db.py` with an asyncpg pool, `acquire()` helper, and small typed query functions.
5. Implement `auth.py` exporting both:
   - `get_agent(req: Request) -> Agent` for FastAPI `Depends`. Reads `Authorization: Bearer <k>`.
   - `ApiKeyMiddleware(Middleware)` for FastMCP. Reads URL path segment after `/mcp/` (set via FastMCP's path-routing) **and** `X-API-Key` / `Authorization` headers.
   - Both bcrypt-verify against `agents.key_hash` and set `agent_id` on the request/context state.
6. Implement `services/projects.py` with `create_project`, `list_projects_for_agent`, `get_project`.
7. Implement `routes_rest.py` for `POST /v1/projects` and `GET /v1/projects`.
8. Implement `mcp_server.py` registering `start_research` and `list_projects` tools (the rest in subsequent half-days). Use Pydantic models for inputs.
9. `main.py`: build FastAPI app, mount `mcp.http_app(path="/mcp/{api_key}")` at `/mcp/{api_key}` via FastAPI route, include REST router, expose `/healthz`. Configure CORS for `https://margin.<tld>`.

**Acceptance criteria.**

- `curl -H "Authorization: Bearer ag_demo_..." -X POST http://localhost:8080/v1/projects -d '{"topic":"x","depth":"standard"}'` returns a `project_id`.
- `npx @modelcontextprotocol/inspector` connects to `http://localhost:8080/mcp/<key>` and lists `start_research` and `list_projects`.
- A second start_research call followed by list_projects returns both, scoped to the agent.

### Day 1, afternoon (4 h) — findings, citations, embeddings

**Goals.** All write tools work. Embeddings flow through. R2 archival works. Idempotency by content hash works. Dedup protects free tiers.

**Tasks.**

1. `embeddings.py`: `async def embed(texts: list[str], input_type: str = "document") -> list[list[float]]`. Primary: Voyage `voyage-3.5-lite` at 1024d, truncate to 768d via slicing then **L2-renormalize** (required after slicing — pgvector's `<=>` cosine distance assumes unit-norm vectors). Fallback (any exception): lazy-load `BAAI/bge-small-en-v1.5` via `sentence-transformers`, encode with `normalize_embeddings=True`, zero-pad 384→768, L2-renormalize. Cache in-process by `sha256(text+input_type)` for the lifetime of the request batch. Callers: `add_finding` passes `input_type="document"`; `query_findings` passes `"query"`. See the canonical implementation in §9.
2. `services/findings.py`: implement `add_finding` with the dedup-on-content-hash logic. Embed once, INSERT once, emit one event row. The CHECK on `confidence` is enforced server-side too; reject early.
3. `services/citations.py`: `cite()` runs `httpx.get`, calls `trafilatura.extract(html, output_format="markdown", with_metadata=True, favor_precision=True)`, hashes via `hashlib.sha256(" ".join(md.split()).encode())`, uploads HTML to R2 with key `pages/<page_hash>.html` and `Content-Type: text/html`. Wraps R2 errors so the citation is still recorded with `fetch_status=0`.
4. `storage.py`: boto3 client with `endpoint_url=https://<acct>.r2.cloudflarestorage.com`, `region_name="auto"`. One method: `put_html(key, html_bytes) -> None`. One method: `signed_get(key, ttl=604800) -> str`.
5. Add `query_findings`, `branch_project`, `request_human_review` to `services/` and to both routers.
6. `services/reports.py`: implement `publish_report` markdown renderer (no LLM yet — naive grouping by confidence buckets is fine for the gate).
7. Wire all eight tools into `mcp_server.py`. Each tool description follows the §4 template precisely (imperative, when/when-not, examples). Add tool annotations: `add_finding`, `cite`, `start_research`, `branch_project`, `request_human_review`, `publish_report` are `destructiveHint: false, idempotentHint: false (true for add_finding via dedup)`; `query_findings` and `list_projects` are `readOnlyHint: true`.

**Acceptance criteria.**

- A scripted client makes 5 `add_finding` calls, two of which have identical claim+evidence; the second returns `deduped: true` and the same `finding_id`.
- `query_findings` with `"cold start"` returns the relevant finding above the unrelated ones.
- `cite()` against a real article URL produces a `citation_id`, the cleaned markdown is non-empty, and `s3:ListObjects` shows the HTML in R2.
- `publish_report` returns a URL whose body contains all confirmed findings rendered as markdown.

### Day 2, morning (4 h) — frontend, deploy, custom domain

**Goals.** Backend runs on Koyeb at a public HTTPS URL. Next.js landing + dashboard are live on Cloudflare Pages. Domain is wired. Claude Desktop can install the connector and call all eight tools.

**Tasks.**

1. **Backend deploy.** Push to GitHub. Create Koyeb app, point at the repo, set env vars (§8), build with `Dockerfile`, expose port 8080. Verify `https://margin-api-<id>.koyeb.app/healthz` returns 200.
2. **Domain.** Buy `margin.<tld>` (recommend `.dev` for credibility, ~$11/yr at Cloudflare Registrar; fall back to `.xyz` at $0.99 if budget is hard $0). Add DNS at Cloudflare:
   - `margin.<tld>` → CNAME to Cloudflare Pages.
   - `api.margin.<tld>` → CNAME to Koyeb app.
3. **Frontend.** Scaffold `apps/web` with `create-next-app`. Implement `Hero`, `McpInstall` (renders `https://api.margin.<tld>/mcp/<key>` once the user has a key), `CodeBlock`, `ActivityTimeline` (uses `EventSource` against `/v1/events?since=...`).
4. Build the dashboard at `/app`: passwordless email magic link (FastAPI sends a 6-digit code via Resend free tier or just shows it in the response for demo), creates owner+agent, displays the connector URL with one-click copy. Show last 50 events in the timeline.
5. Render the report viewer at `/r/[slug]` by fetching `GET /v1/reports/<slug>` and rendering markdown via `react-markdown`.
6. `next.config.ts` with `output: 'export'`, deploy to Cloudflare Pages via the Wrangler GitHub Action.
7. **Wire Claude Desktop.** In Claude.ai → Settings → Connectors → Add custom connector, paste `https://api.margin.<tld>/mcp/<key>`. Verify Margin appears in the connector list and tools are callable.

**Acceptance criteria.**

- Visiting `https://margin.<tld>` from a fresh browser shows the hero, copyable MCP install command, and an embedded video placeholder.
- Signing in with email and clicking the dashboard shows a real API key and timeline.
- Claude.ai can connect to the MCP server and call `start_research` end-to-end with the response visible in the timeline within 2 seconds.

### Day 2, afternoon (4 h) — polish, demo, application

**Goals.** Demo recorded. README is YC-partner-ready. Application submitted before the May 4 deadline.

**Tasks.**

1. **Polish gates.** Add LLM-generated TOC to `publish_report` using Groq llama-3.3-70b. Add `archive_url` (signed R2) to citations in published reports. Add basic rate-limiting (60 req/min per agent) using a simple in-memory leaky-bucket — enough for a demo.
2. **Record demo.** Single take, 90 s, screen + voice (no founder face on this video — that one is for the YC form). Script in §10. Use OBS or QuickTime, export H.264 MP4, commit to `apps/web/public/demo.mp4`.
3. **Record YC founder video.** 60 s, founder on camera, single take, no editing — per Aaron Epstein's advice that "the more professional you make your video, the more it's probably going to make them think you're a little too slick." Script in §10.
4. **Write README.** Use the copy in §11.
5. **Write the YC application.** Use the copy in §12.
6. **Submit.** ycombinator.com/apply, before May 4 8 PM PT.

**Acceptance criteria.**

- `apps/web/public/demo.mp4` plays inline on the landing page, shows Claude using all eight tools across two sessions.
- `README.md` has a working `Add to Claude` link and a copy-paste curl command that returns 200 against the live API.
- The YC application is submitted with the live URL `margin.<tld>` linked.

---

## 7. Hosting and deployment specifics — chosen services and why

| Slot | Choice | Rationale | Fallback |
|---|---|---|---|
| Backend compute | **Koyeb free instance** | Persistent process, no credit card, commercial use allowed, scales to zero only after 1 h idle. Render free sleeps after 15 min and cold-starts in 30+ s, which breaks Claude's MCP handshake. Railway and Fly.io no longer have free tiers. | Fly.io shared-cpu-1x@256MB at ~$2/mo if Koyeb cold starts during the demo. |
| Frontend | **Cloudflare Pages** | Unlimited bandwidth, no commercial-use restriction (Vercel Hobby explicitly bans commercial use, which a YC startup application is), 100k Functions/day, no hard pause cliff. | Vercel Hobby for the development phase only. |
| Postgres + vectors | **Neon free** | Never paused on inactivity (unlike Supabase's 7-day pause), pgvector built-in, 0.5 GB per project, commercial OK, no credit card. The combination of "always-reachable" and "pgvector in the same DB" eliminates an entire service. | Supabase free with a GitHub Action keep-alive ping every 6 days. |
| Blob storage | **Cloudflare R2** | 10 GB free, zero egress forever, S3-compatible boto3. A YC partner clicking the demo report 50 times is free; on Backblaze or S3 it isn't. | Backblaze B2 with Cloudflare in front. |
| Auth | **Roll-your-own bcrypt API keys** in `agents` table | Clerk's M2M tokens started billing March 16 2026; agent users don't need OAuth flows. ~30 lines of code, zero recurring cost. | None needed. |
| Embeddings | **Voyage 3.5-lite @ 1024d, truncated to 768d + L2-renormalized** | Best-in-class retrieval quality (top of MTEB English), 200M free tokens (effectively bottomless for our volume of ~100-200 embeddings/day), no credit card required, independent provider — clean story for a product storing third-party research data. | `sentence-transformers/bge-small-en-v1.5` running locally in the Koyeb container (384d, no API call, never throttles). |
| LLM (light) | **Groq llama-3.3-70b-versatile** | 30 RPM, 14.4k RPD, no credit card, ~500 tok/s. Used only for the report TOC at publish time. The fast streaming makes the publish moment feel instant in the demo. | Groq `llama-3.1-8b-instant` for overflow; or skip the TOC entirely and ship the naive markdown grouping. |
| Web fetch + extraction | **httpx + trafilatura** | Trafilatura beats readability-lxml and newspaper3k in independent benchmarks (F1 0.94+); built-in markdown output; no Playwright required. | Add Playwright only if a target source is JS-rendered. |
| CI/CD | **GitHub Actions** | Free unlimited minutes for public repos. | Built-in Pages/Koyeb Git deploys for redundancy. |
| Domain | **`.dev` from Cloudflare Registrar (~$11/yr)** | Auto-HTTPS, recognizable as a developer/AI product, at-cost pricing. The single line item worth a buck for YC credibility. | `.xyz` at $0.99 from Namecheap; or `*.koyeb.app` + `*.pages.dev` for $0. |

**Hard avoid list, with reasons:**

- Vercel Hobby — TOS bans commercial use; pauses on quota with no overage.
- Supabase free — 7-day inactivity pause kills the demo URL.
- Render free — 15-minute sleep and 30 s+ cold starts break MCP.
- Railway, Fly.io — no real free tier in 2026.
- Firebase Storage — removed from the Spark plan in February 2026.
- Freenom domains — effectively defunct.
- Clerk M2M tokens — started billing March 16 2026.
- Gemini — not used. Voyage covers embeddings; Groq covers the LLM.

---

## 8. Environment variables and secrets

A single `.env.example` file lives at the repo root. The api reads it via `pydantic-settings`. The web app uses only `NEXT_PUBLIC_API_BASE`.

```
# --- API service ---
DATABASE_URL=postgresql://<user>:<pw>@<host>/<db>?sslmode=require
JWT_SECRET=<32 random bytes hex>           # for short-lived dashboard sessions
PUBLIC_BASE_URL=https://margin.dev
API_BASE_URL=https://api.margin.dev

# Embeddings (Voyage)
VOYAGE_API_KEY=pa-...
VOYAGE_EMBED_MODEL=voyage-3.5-lite
VOYAGE_EMBED_DIM_RAW=1024                  # native output dim
EMBED_DIM=768                              # what we store after truncate + renormalize

# LLM (Groq)
GROQ_API_KEY=gsk_...
GROQ_MODEL=llama-3.3-70b-versatile

# Cloudflare R2
R2_ACCOUNT_ID=...
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_BUCKET=margin-pages
R2_ENDPOINT=https://<acct>.r2.cloudflarestorage.com

# Email (optional; skip and just print the magic-link code in dev)
RESEND_API_KEY=re_...

# Web app
NEXT_PUBLIC_API_BASE=https://api.margin.dev
```

**Secrets handling rules.**

- All secrets stored in Koyeb's secret manager and Cloudflare Pages' environment variables. Never committed.
- A `.env.example` is committed; `.env` is in `.gitignore`.
- API keys minted by us are bcrypt-hashed on insert. Plaintext is shown to the user **once** , then never again.
- R2 credentials are scoped to the `margin-pages` bucket only.

---

## 9. Architecture notes that matter

**The agent identity is the URL path.** Because Claude.ai's connector UI does not let users set headers, the API key lives in the path segment: `https://api.margin.dev/mcp/ag_live_aB12...`. FastMCP's middleware extracts it. We document this clearly in the README; we also support `Authorization: Bearer` for API consumers (Cursor, MCP Inspector, our own SDK).

**Stateless MCP.** We run FastMCP with `stateless_http=True`. No sticky sessions needed; horizontal scale is trivial; we lose elicitation/sampling capabilities, which we don't use. This is the explicit FastMCP recommendation for production multi-instance deployments.

**SSE for the dashboard, not for MCP.** The dashboard timeline subscribes to `GET /v1/events?since=` and streams via plain SSE. The MCP transport uses `POST /mcp` for JSON-RPC and never opens a persistent SSE channel. Server uses Postgres `LISTEN/NOTIFY` to fan out events to connected SSE clients.

**Provenance pipeline.** When an agent calls `cite()`: fetch with httpx → extract with trafilatura → hash cleaned markdown → upload raw HTML to R2 → write row. On `publish_report`, generate signed R2 URLs for each citation and embed them. The agent gets durable receipts.

**Embedding economics.** 100 findings/day × ~500 tokens = 50k tokens/day, well under Voyage's 200M-token free pool — we'd hit it after roughly 11 years of continuous use at this rate. We dedupe on insert via `content_hash`, so an agent loop can't burn budget. We truncate Voyage's 1024-dim output to 768 dims and **L2-renormalize after truncation** (this step is non-optional — slicing breaks the unit-norm property and pgvector's `<=>` cosine distance assumes normalized vectors for best behavior). HNSW index handles up to ~1M rows comfortably. If Voyage ever errors out, we degrade to local `bge-small-en-v1.5` running in the Koyeb container — slower per call but never throttles, and 384d is fine for our scale (we just pad to 768 with zeros and renormalize so the column dimension stays stable).

### Reference implementation: `embeddings.py`

This is the file the coding agent should write — it is the contract for §9 above.

```python
import asyncio
import hashlib
import math
import os
from typing import Sequence

import voyageai

EMBED_DIM = 768

_voyage = voyageai.AsyncClient(api_key=os.environ["VOYAGE_API_KEY"])
_local_model = None  # lazy-loaded on fallback


def _l2_normalize(vec: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in vec))
    if n == 0:
        return vec
    return [x / n for x in vec]


def _truncate_and_renormalize(vec: list[float], target_dim: int) -> list[float]:
    return _l2_normalize(vec[:target_dim])


async def _embed_voyage(texts: Sequence[str], input_type: str) -> list[list[float]]:
    resp = await _voyage.embed(
        texts=list(texts),
        model=os.environ.get("VOYAGE_EMBED_MODEL", "voyage-3.5-lite"),
        input_type=input_type,  # "document" on insert, "query" on search
    )
    return [_truncate_and_renormalize(e, EMBED_DIM) for e in resp.embeddings]


def _ensure_local():
    global _local_model
    if _local_model is None:
        from sentence_transformers import SentenceTransformer
        _local_model = SentenceTransformer("BAAI/bge-small-en-v1.5")
    return _local_model


async def _embed_local(texts: Sequence[str]) -> list[list[float]]:
    model = _ensure_local()
    raw = await asyncio.to_thread(model.encode, list(texts), normalize_embeddings=True)
    out = []
    for v in raw.tolist():
        # bge-small is 384d; pad to EMBED_DIM with zeros, then renormalize
        padded = list(v) + [0.0] * (EMBED_DIM - len(v))
        out.append(_l2_normalize(padded))
    return out


async def embed(texts: Sequence[str], input_type: str = "document") -> list[list[float]]:
    """Primary: Voyage 3.5-lite. Fallback: local bge-small. Always returns 768-d unit vectors."""
    if not texts:
        return []
    try:
        return await _embed_voyage(texts, input_type)
    except Exception:
        return await _embed_local(texts)
```

Two consequences worth knowing. First, `add_finding` should call `embed([claim + " " + evidence], input_type="document")`; `query_findings` should call `embed([semantic_query], input_type="query")`. Voyage uses these hints to specialize representations and it does measurably help retrieval. Second, the bge fallback's 384→768 zero-padding is a hack; it preserves the column dimension so we don't have to rebuild the HNSW index, but quality drops. If we ever stay on the fallback long enough to care, swap `bge-small` for `bge-base-en-v1.5` (768 native) — same file, two-line change.

**Idempotency.** Every write tool is idempotent on a sensible key: `add_finding` on `(project_id, content_hash)`; `cite` on `(finding_id, page_hash)`; `start_research` is **not** idempotent on `topic` (deliberate — agents should be free to start parallel investigations of the same topic). This protects free-tier costs against an agent loop.

**Tool description discipline.** Per Anthropic's writing-tools-for-agents guidance: imperative voice, explicit when/when-not, an inline example, structured input + output schemas, tool annotations on every tool. We deliberately keep the tool count to **eight** because the GitHub MCP cautionary tale (43 tools, ~17k tokens of context overhead) showed how much agents pay for surface bloat.

---

## 10. Demo scripts

### 10.1 Product demo (90 s, on the landing page, screen recording)

**Setup before recording.** Two Claude.ai conversations queued. A blank Margin dashboard tab. Agent key already minted. The connector URL pre-pasted in Claude.ai connectors.

**Script (voice-over over screen capture):**

> "This is Margin. It's a research workspace where the user is an AI agent.
>
> [0:08] I install it in Claude with one URL — paste, save. Eight tools show up.
>
> [0:15] I say: research the state of free MCP hosting in April 2026. Claude calls `start_research`. The dashboard, on the right, shows it live.
>
> [0:30] Claude browses, then calls `add_finding` ten times — each one a typed claim, evidence, source, and confidence. Margin embeds each finding into pgvector and archives the source HTML to R2 keyed by content hash.
>
> [0:50] I close the chat. I open a brand-new Claude conversation. I say: continue the MCP research and find contradictions. Claude calls `list_projects`, then `query_findings` with `cold start times`. It pulls the relevant findings back from yesterday — semantically.
>
> [1:10] It finds two sources that disagree on Koyeb's cold-start time. It calls `branch_project` to fork an investigation, resolves the contradiction, then `request_human_review`.
>
> [1:25] I approve. It calls `publish_report`. Here is the report — markdown, every claim cited, every source archived, a stable public URL.
>
> [1:30] Margin is the workspace. The agent did the work. The state outlived the model."

### 10.2 Founders' video (60 s, for the YC application form)

Per Aaron Epstein's guidance: founder on camera, smile, single take, no editing.

> "Hi YC, I'm `<name>`. I'm building Margin: a research workspace whose primary user is an AI agent.
>
> Aaron's RFS says: agents need APIs, MCPs, and CLIs, and every category of software needs to be rebuilt for them. The category I'm rebuilding is the research workspace — the Notion page or Jupyter notebook of the agent era.
>
> Today, agents do research and then forget it the moment the chat ends. Memory tools like Mem0 and Zep store facts. Browsers like Browserbase give agents a body. Nobody owns the artifact — the structured, citation-backed, queryable document the agent produces and hands off across sessions.
>
> Margin does. Eight primitives, MCP and REST, free tier from day one, paid the moment a team needs to share. I built the MVP solo over a weekend; it's live at margin.dev right now and Claude can use it end to end.
>
> I'd love to come build this in Summer 2026. Thanks."

---

## 11. README and landing page copy

### 11.1 Landing page (`apps/web/app/page.tsx`)

**Hero (above the fold):**

> # The research workspace for AI agents.
>
> Margin gives your agents persistent, typed, citation-backed state across sessions and models. Connect over MCP or REST. Eight primitives. Free for solo developers.
>
> **Add to Claude →** `https://api.margin.dev/mcp/<your-key>` _(copy)_
>
> ```bash
> curl -X POST https://api.margin.dev/v1/projects \
>   -H "Authorization: Bearer $MARGIN_KEY" \
>   -d '{"topic":"free-tier MCP hosting","depth":"thorough"}'
> # → { "project_id": "p_K1aZ9b...", "dashboard_url": "..." }
> ```
>
> [Watch a 90-second demo →] [Read the docs →] [GitHub →]

**Below the fold, three sections:**

1. **What agents get** — eight primitives listed with one-line descriptions and a copyable example for each.
2. **State that survives the model** — a 200-word explainer with a diagram: agent A in Claude → finding f1 → agent B in Cursor next week → `query_findings` → f1 returns. Same workspace, different model.
3. **Built for the RFS** — a quote block from Aaron Epstein's RFS, followed by "Margin is the picks-and-shovels."

### 11.2 README.md

````markdown
# Margin

**The research workspace for AI agents.** Eight primitives. MCP + REST. Free tier.

## Quickstart in 60 seconds

1. Get a key: https://margin.dev/app
2. Add to Claude: paste `https://api.margin.dev/mcp/<key>` into Settings → Connectors.
3. Or use REST:

   ```bash
   curl -X POST https://api.margin.dev/v1/projects \
     -H "Authorization: Bearer $MARGIN_KEY" \
     -d '{"topic":"x","depth":"standard"}'
   ```
````

## The eight primitives

| Tool                                                            | Purpose                                   |
| --------------------------------------------------------------- | ----------------------------------------- |
| `start_research(topic, depth, deadline?)`                       | Begin a research project.                 |
| `add_finding(project_id, claim, evidence, source?, confidence)` | Record a typed claim with evidence.       |
| `cite(finding_id, url, excerpt)`                                | Attach a citation; we archive the source. |
| `query_findings(project_id, semantic_query)`                    | Semantic recall over prior findings.      |
| `branch_project(project_id, reason)`                            | Fork into a sub-investigation.            |
| `request_human_review(project_id, reason)`                      | Pause for human approval.                 |
| `publish_report(project_id, format)`                            | Render a citation-backed report.          |
| `list_projects()`                                               | List the calling agent's projects.        |

## Why Margin

Memory layers store facts. Browsers give agents bodies. Sandboxes give them hands.
Margin is the **workspace** — the durable, structured artifact the agent produces
and hands off across sessions. Built for Aaron Epstein's "Software for Agents" RFS.

## Self-host

```bash
docker run -p 8080:8080 \
  -e DATABASE_URL=... -e VOYAGE_API_KEY=... -e GROQ_API_KEY=... \
  ghcr.io/<you>/margin-api:latest
```

MIT licensed.

```

---

## 12. YC application copy

**Company name (50 chars):** Margin

**One-liner:** "The research workspace for AI agents."

**What is your company going to make?**
> Margin is a hosted research workspace whose primary user is an AI agent. Agents connect via MCP or REST and call eight primitives — start_research, add_finding, cite, query_findings, branch_project, request_human_review, publish_report, list_projects — to build durable, typed, citation-backed research projects that survive sessions, models, and human handoffs. The agent does the work; Margin owns the artifact.

**Why now?**
> Aaron Epstein's Summer 2026 RFS says agents need "APIs, MCPs, and CLIs" with "thorough documentation" and that "every major category of software that people use today needs to be rebuilt for agents." The agent-infra layer below us is funded — Mem0 raised $24M for memory, Zep similar, Browserbase Series B at $300M, Composio $29M — but **the research workspace category is empty**. NotebookLM and Claude Projects are clients for humans. Memory tools store facts, not artifacts. Skills are procedural, not persistent. The lane is open and MCP adoption (270+ servers in the Docker MCP Catalog as of February 2026) is the distribution channel.

**Progress (for the form's progress field):**
> Live at https://margin.dev. Built solo in 2 days. Open-source MIT on GitHub. Eight MCP tools and a REST mirror, deployed on Koyeb + Cloudflare + Neon at $0/mo recurring. Demo video shows Claude Desktop using Margin across two separate sessions to research, contradict, branch, review, and publish a report. Real users to be added the week of submission.

**How will you make money?**
> Free for solo developers (one agent, 1k findings, 100MB storage). $20/mo Pro for ten agents and 100k findings; $200/mo Team adds shared projects and SSO. Storage is the natural lock-in — Aaron Epstein's pricing rule of "charge from day one or freemium with clear lock-in" maps directly onto a research workspace where the artifact's value compounds with use.

**Founder bio impressive line (one per founder):**
> *(Replace with real)* "Built and shipped <thing> with <metric>; previously <role at credible co>; deepest experience with <relevant stack>."

**Other ideas:**
> An "MCP gateway" that proxies and rate-limits multiple MCP servers with one key, exposing a billing/audit layer. An MCP tool registry with semantic search for agents discovering tools at runtime. A CLI-first agent eval harness that lives next to the workspace.

**Hacker question:**
> *(Honest, concrete, non-tech, ~80 words.)*

---

## 13. Risk register and what to deprioritize if behind schedule

| Risk | Likelihood | Impact | Mitigation | If it bites: cut |
|---|---|---|---|---|
| Koyeb scales to zero between demo retakes | Medium | Demo cold-starts | Send a heartbeat from the dashboard every 30 min during demo day | Move to Fly.io shared-cpu at $2/mo |
| Voyage free-tier throttles at the wrong moment | Low | Findings fall back to local bge-small (slower, lower quality) | Local `bge-small-en-v1.5` fallback wired in `embeddings.py` from day 1; it never throttles | Warm the local model at boot if we expect heavy load |
| Claude.ai connector UI changes between dev and demo | Low | Install path differs | Document both Claude.ai and Claude API Managed Agents paths | Show the REST curl path in the demo instead |
| pgvector HNSW build slow on Neon free | Low | Slow first query | Index built once at migration time | Switch to ivfflat |
| trafilatura fails on JS-rendered sources | Medium | Citation has empty markdown | Citation row still inserted with `fetch_status=0`; agent can retry | Skip extraction; store raw HTML only |
| Domain DNS not propagated in time | Low | Demo on `*.koyeb.app` | Buy domain on day 1 morning | Use platform subdomains |
| Magic-link email delivery flaky | Low | Sign-in friction | Print the code in the API response in dev mode | Skip email entirely; show the API key on a "claim a key" public page |
| MCP spec or Claude connector behavior shifts pre-demo | Low | Reconnect needed | Pin to spec `2025-11-25`; FastMCP 2.x | Demo via MCP Inspector instead of Claude |

**If you're behind at end of Day 2 morning, cut in this order:**

1. The dashboard's live SSE timeline — replace with a static "last 50 events" polling table.
2. The LLM-generated TOC in `publish_report` — keep the naive markdown grouping.
3. The `branch_project` and `request_human_review` tools' UI surfaces — they still work over MCP, just no special dashboard treatment.
4. The Python SDK in `packages/sdk-py/` — pure polish.
5. The dedicated docs page at `/docs` — link directly to `/v1/openapi.json`.

**Never cut:** the eight MCP tools end-to-end, the citation archival to R2, the live URL working from a Claude.ai connector install, the demo video.

---

## Conclusion: what makes this spec executable

The build is **scoped to one developer for two days at $0/month**, with every choice between two services already made and justified by current April 2026 free-tier reality — not by 2024 tutorials. The data model fits in 200 lines of SQL. The API surface is eight MCP tools mirrored as eight REST endpoints, both backed by the same services layer. The hosting plan survives a YC partner clicking the demo URL on day 5. The deferred-work order is explicit: cut polish, never cut the primitives or the archive trail.

The strategic bet is simple: **memory tools sell facts; Margin sells artifacts.** Aaron Epstein's RFS asks for "APIs, MCPs, and CLIs" and Margin is all three on day one. The category is empty; the distribution channel (the MCP client install graph) is exploding; the cost basis is zero. Two days to ship; six days to the May 4 deadline. Build it.
```
