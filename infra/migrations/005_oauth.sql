-- OAuth 2.1 + Dynamic Client Registration support for the MCP transport.
--
-- Three tables:
--   oauth_clients          — registered clients (Claude.ai, Cursor, custom SDKs)
--   oauth_codes            — short-lived authorization codes (single-use, 10-min TTL)
--   oauth_refresh_tokens   — long-lived refresh tokens (rotated on use, revocable)
--
-- Access tokens are JWTs (no DB row); they're verified via signature + audience
-- on the MCP hot path with no DB hit. See apps/api/src/margin_api/oauth/tokens.py.

CREATE TABLE IF NOT EXISTS oauth_clients (
    client_id            TEXT PRIMARY KEY DEFAULT ('cli_' || encode(gen_random_bytes(12), 'hex')),
    client_name          TEXT NOT NULL,
    redirect_uris        TEXT[] NOT NULL,
    grant_types          TEXT[] NOT NULL DEFAULT ARRAY['authorization_code', 'refresh_token'],
    response_types       TEXT[] NOT NULL DEFAULT ARRAY['code'],
    token_endpoint_auth_method TEXT NOT NULL DEFAULT 'none',
    logo_uri             TEXT,
    client_uri           TEXT,
    software_id          TEXT,
    software_version     TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at           TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_oauth_clients_active
    ON oauth_clients(client_id) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS oauth_codes (
    code_hash             TEXT PRIMARY KEY,
    client_id             TEXT NOT NULL REFERENCES oauth_clients(client_id) ON DELETE CASCADE,
    owner_id              TEXT NOT NULL REFERENCES owners(owner_id) ON DELETE CASCADE,
    agent_id              TEXT NOT NULL REFERENCES agents(agent_id) ON DELETE CASCADE,
    redirect_uri          TEXT NOT NULL,
    code_challenge        TEXT NOT NULL,
    code_challenge_method TEXT NOT NULL,
    scope                 TEXT,
    resource              TEXT,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at            TIMESTAMPTZ NOT NULL,
    used_at               TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS oauth_refresh_tokens (
    token_hash    TEXT PRIMARY KEY,
    client_id     TEXT NOT NULL REFERENCES oauth_clients(client_id) ON DELETE CASCADE,
    agent_id      TEXT NOT NULL REFERENCES agents(agent_id) ON DELETE CASCADE,
    owner_id      TEXT NOT NULL REFERENCES owners(owner_id) ON DELETE CASCADE,
    scope         TEXT,
    issued_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at    TIMESTAMPTZ NOT NULL,
    revoked_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_oauth_refresh_active
    ON oauth_refresh_tokens(agent_id) WHERE revoked_at IS NULL;
