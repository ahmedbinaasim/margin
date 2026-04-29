-- Margin initial schema. See SPEC.md §3.
-- Postgres 16 + pgvector. Idempotent: safe to apply on a fresh database.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;

-- Owners are humans. One owner, many agents (each with its own API key).
CREATE TABLE IF NOT EXISTS owners (
    owner_id    TEXT PRIMARY KEY DEFAULT ('o_' || encode(gen_random_bytes(8), 'hex')),
    email       CITEXT UNIQUE NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- An "agent" is an API-key-bearing principal. The same human can have many.
CREATE TABLE IF NOT EXISTS agents (
    agent_id     TEXT PRIMARY KEY DEFAULT ('ag_' || encode(gen_random_bytes(10), 'hex')),
    owner_id     TEXT NOT NULL REFERENCES owners(owner_id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    key_hash     TEXT NOT NULL,
    key_prefix   TEXT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_agents_owner ON agents(owner_id);
CREATE INDEX IF NOT EXISTS idx_agents_prefix ON agents(key_prefix);

-- Magic-link codes for the dashboard sign-in flow.
CREATE TABLE IF NOT EXISTS auth_codes (
    code_hash  TEXT PRIMARY KEY,
    email      CITEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at    TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_auth_codes_email ON auth_codes(email);

-- A research project, owned by exactly one agent.
CREATE TABLE IF NOT EXISTS projects (
    project_id    TEXT PRIMARY KEY DEFAULT ('p_' || encode(gen_random_bytes(8), 'hex')),
    agent_id      TEXT NOT NULL REFERENCES agents(agent_id) ON DELETE CASCADE,
    topic         TEXT NOT NULL,
    depth         TEXT NOT NULL CHECK (depth IN ('quick','standard','thorough')),
    deadline      TIMESTAMPTZ,
    parent_id     TEXT REFERENCES projects(project_id),
    branch_reason TEXT,
    status        TEXT NOT NULL DEFAULT 'active'
                  CHECK (status IN ('active','review_requested','published','archived')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_projects_agent ON projects(agent_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_projects_parent ON projects(parent_id);

-- A typed finding: claim + evidence + source + confidence.
-- Embedding column is voyage-3.5-lite 1024d truncated to 768d and L2-renormalized.
CREATE TABLE IF NOT EXISTS findings (
    finding_id   TEXT PRIMARY KEY DEFAULT ('f_' || encode(gen_random_bytes(8), 'hex')),
    project_id   TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    agent_id     TEXT NOT NULL REFERENCES agents(agent_id),
    claim        TEXT NOT NULL,
    evidence     TEXT NOT NULL,
    source_url   TEXT,
    confidence   REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    contradicts  TEXT REFERENCES findings(finding_id),
    embedding    VECTOR(768),
    content_hash TEXT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (project_id, content_hash)
);
CREATE INDEX IF NOT EXISTS idx_findings_project ON findings(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_findings_hash ON findings(content_hash);
CREATE INDEX IF NOT EXISTS idx_findings_contradicts ON findings(contradicts);
CREATE INDEX IF NOT EXISTS idx_findings_embedding ON findings USING hnsw (embedding vector_cosine_ops);

-- Citations are immutable evidence rows pointing at cached source HTML.
CREATE TABLE IF NOT EXISTS citations (
    citation_id   TEXT PRIMARY KEY DEFAULT ('c_' || encode(gen_random_bytes(8), 'hex')),
    finding_id    TEXT NOT NULL REFERENCES findings(finding_id) ON DELETE CASCADE,
    url           TEXT NOT NULL,
    canonical_url TEXT NOT NULL,
    excerpt       TEXT NOT NULL,
    page_hash     TEXT NOT NULL,
    r2_key        TEXT,
    fetched_at    TIMESTAMPTZ,
    fetch_status  INT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (finding_id, page_hash)
);
CREATE INDEX IF NOT EXISTS idx_citations_finding ON citations(finding_id);
CREATE INDEX IF NOT EXISTS idx_citations_pagehash ON citations(page_hash);

-- Human review requests.
CREATE TABLE IF NOT EXISTS reviews (
    review_id    TEXT PRIMARY KEY DEFAULT ('rv_' || encode(gen_random_bytes(8), 'hex')),
    project_id   TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    reason       TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending'
                 CHECK (status IN ('pending','approved','rejected')),
    decided_at   TIMESTAMPTZ,
    decided_note TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_reviews_project ON reviews(project_id);

-- Published reports.
CREATE TABLE IF NOT EXISTS reports (
    report_id   TEXT PRIMARY KEY DEFAULT ('rp_' || encode(gen_random_bytes(8), 'hex')),
    project_id  TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    format      TEXT NOT NULL CHECK (format IN ('markdown','html','json')),
    body        TEXT NOT NULL,
    public_slug TEXT UNIQUE NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_reports_slug ON reports(public_slug);

-- Append-only event log; powers the dashboard timeline via SSE.
CREATE TABLE IF NOT EXISTS events (
    event_id   BIGSERIAL PRIMARY KEY,
    agent_id   TEXT NOT NULL REFERENCES agents(agent_id) ON DELETE CASCADE,
    project_id TEXT REFERENCES projects(project_id) ON DELETE CASCADE,
    kind       TEXT NOT NULL,
    payload    JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_events_agent_time ON events(agent_id, event_id DESC);
CREATE INDEX IF NOT EXISTS idx_events_project_time ON events(project_id, event_id DESC);
