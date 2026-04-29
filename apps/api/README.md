# margin-api

FastAPI + FastMCP service backing Margin. See `../../SPEC.md` for design and the eight primitives.

## Local dev

```bash
# 1. start Postgres + pgvector
docker compose up -d postgres   # from repo root

# 2. apply migrations
DATABASE_URL=postgresql://margin:margin@localhost:5432/margin python ../../infra/migrations/run.py

# 3. seed a demo agent
DATABASE_URL=postgresql://margin:margin@localhost:5432/margin python ../../infra/seed.py

# 4. install + run the api
uv sync --all-extras
uv run uvicorn margin_api.main:app --reload --port 8080
```

## Tests

```bash
uv run pytest                                  # unit + fast integration
uv run pytest -m slow                          # also load local bge-small
uv run pytest -m live                          # hit real Voyage/Groq/R2 (needs keys)
```
