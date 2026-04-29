"""FastAPI app factory + FastMCP mount.

Single source of business logic lives in services/*.py. Both REST handlers
(routes_rest.py) and MCP tools (mcp_server.py) call those services.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import close_pool, init_pool


def _configure_logging() -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
        cache_logger_on_first_use=True,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    _configure_logging()
    await init_pool()
    try:
        yield
    finally:
        await close_pool()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Margin",
        description="Agent-native research workspace. Eight primitives over MCP and REST.",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.public_base_url, "http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # REST router
    from .routes_rest import router as rest_router

    app.include_router(rest_router)

    # MCP mount (FastMCP HTTP app at /mcp/{api_key}). The app itself routes
    # JSON-RPC; the {api_key} segment is captured by an ASGI middleware on
    # the FastMCP side.
    from .mcp_server import build_mcp_app

    mcp_app = build_mcp_app()
    if mcp_app is not None:
        app.mount("/mcp", mcp_app)

    @app.get("/healthz")
    async def healthz() -> dict[str, object]:
        from .db import acquire

        checks: dict[str, object] = {"status": "ok"}
        try:
            async with acquire() as conn:
                await conn.fetchval("SELECT 1")
            checks["db"] = "ok"
        except Exception as e:
            checks["status"] = "degraded"
            checks["db"] = f"error: {type(e).__name__}"

        from . import storage

        checks["r2"] = "configured" if storage.is_enabled() else "disabled"
        checks["voyage"] = "configured" if get_settings().voyage_api_key else "disabled"
        checks["groq"] = "configured" if get_settings().groq_api_key else "disabled"
        return checks

    return app


app = create_app()
