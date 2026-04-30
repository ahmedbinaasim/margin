-- Soft-delete for agents so we can revoke API keys without losing the
-- referential integrity of findings/citations/events that reference them.
-- A partial index keeps the auth-key lookup hot-path on active rows only.

ALTER TABLE agents ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_agents_active_prefix
  ON agents (key_prefix)
  WHERE deleted_at IS NULL;
