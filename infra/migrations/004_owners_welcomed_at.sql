-- Track when each owner received their welcome email so we only send it
-- once. NULL = not yet welcomed; populated atomically with the upsert in
-- `services/owners.upsert_owner_and_maybe_welcome` to avoid double-send on
-- concurrent first-logins.

ALTER TABLE owners ADD COLUMN IF NOT EXISTS welcomed_at TIMESTAMPTZ;
