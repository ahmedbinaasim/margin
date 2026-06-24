"""FastMCP server: the eight Margin primitives, Streamable-HTTP, stateless.

Identity comes in over two paths handled by APIKeyPathMiddleware below:

1. **Legacy URL-key** (``/mcp/<api_key>``) — for clients that paste a URL
   minted from the dashboard. The key is bcrypt-verified and resolved to an
   Agent on every request (with a 60s in-process cache).
2. **OAuth Bearer token** (``/mcp`` + ``Authorization: Bearer <jwt>``) — for
   modern MCP clients that follow the OAuth 2.1 + DCR flow. The JWT is
   self-contained: signature + audience + expiry validation, no DB hit.

Both paths land on the same downstream FastMCP app with the resolved Agent
stashed on ``scope["state"]["agent"]``. Tool wrappers read it via
``_agent_from_ctx`` regardless of which path issued it.

Tool descriptions follow SPEC §4.1 verbatim — imperative voice, when/when-not,
inline example. Eight tools, deliberately no more (SPEC §9 — agents pay
context for tool surface).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from fastmcp import Context, FastMCP

from . import models as m
from .auth import Agent, _resolve_key  # type: ignore[reportPrivateUsage]
from .config import get_settings
from .oauth.tokens import verify_access_token
from .rate_limit import check as rate_check
from .services import (
    citations as citations_svc,
)
from .services import (
    findings as findings_svc,
)
from .services import (
    projects as projects_svc,
)
from .services import (
    reports as reports_svc,
)
from .services import (
    reviews as reviews_svc,
)

mcp = FastMCP("margin")


def _agent_from_ctx(ctx: Context):
    """Pull the Agent stashed by APIKeyPathMiddleware out of the request scope."""
    request = ctx.request_context.request  # Starlette Request
    agent = getattr(request, "state", None) and request.state.agent
    if agent is None:
        raise PermissionError("not authenticated")
    return agent


def _human_text(payload: dict[str, Any]) -> str:
    """One-line summary for the MCP ``text`` block. Per Anthropic's tool guidance."""
    keys = ("project_id", "finding_id", "citation_id", "review_id", "report_url", "results")
    parts: list[str] = []
    for k in keys:
        if k in payload:
            v = payload[k]
            if isinstance(v, list):
                parts.append(f"{k}={len(v)}")
            else:
                parts.append(f"{k}={v}")
    return ", ".join(parts) if parts else json.dumps(payload, default=str)[:160]


async def _enforce_rate(agent_id: str) -> None:
    if not await rate_check(agent_id):
        raise PermissionError("rate limited (60/min)")


def _dashboard_url(project_id: str) -> str:
    return f"{get_settings().public_base_url}/app/p/{project_id}"


# ---------- Tool 1: start_research ----------


@mcp.tool(
    name="start_research",
    description=(
        "Begin a new research project. Use this when an agent is starting a "
        "substantive investigation that should persist across turns or sessions. "
        "Do NOT use for one-off questions answerable in a single search.\n\n"
        "Example: start_research(topic='free-tier MCP hosting in 2026', depth='thorough')"
    ),
)
async def start_research(
    topic: str,
    ctx: Context,
    depth: str = "standard",
    deadline: str | None = None,
) -> dict[str, Any]:
    agent = _agent_from_ctx(ctx)
    await _enforce_rate(agent.agent_id)
    parsed = m.StartResearchInput(topic=topic, depth=depth, deadline=deadline)  # type: ignore[arg-type]
    row = await projects_svc.create_project(
        agent_id=agent.agent_id,
        topic=parsed.topic,
        depth=parsed.depth,
        deadline=parsed.deadline,
    )
    out = m.StartResearchOutput(
        project_id=row["project_id"],
        topic=row["topic"],
        depth=row["depth"],
        deadline=row["deadline"],
        created_at=row["created_at"],
        dashboard_url=_dashboard_url(row["project_id"]),
    ).model_dump(mode="json")
    return out


# ---------- Tool 2: add_finding ----------


@mcp.tool(
    name="add_finding",
    description=(
        "Record one factual claim with its supporting evidence in a project. "
        "One claim per call; loop in the agent for multiple. Idempotent on "
        "(project_id, claim+evidence) — repeated identical calls return the "
        "same finding_id with deduped=true.\n\n"
        "Example: add_finding(project_id='p_K1aZ9...', claim='X', evidence='\"...\"', "
        "source='https://...', confidence=0.9)"
    ),
    annotations={"idempotentHint": True, "destructiveHint": False},
)
async def add_finding(
    project_id: str,
    claim: str,
    evidence: str,
    confidence: float,
    ctx: Context,
    source: str | None = None,
    contradicts: str | None = None,
) -> dict[str, Any]:
    agent = _agent_from_ctx(ctx)
    await _enforce_rate(agent.agent_id)

    proj = await projects_svc.get_project(project_id, agent_id=agent.agent_id)
    if proj is None:
        raise ValueError(f"project {project_id} not found for this agent")
    try:
        result = await findings_svc.add_finding(
            agent_id=agent.agent_id,
            project_id=project_id,
            claim=claim,
            evidence=evidence,
            source=source,
            confidence=confidence,
            contradicts=contradicts,
        )
    except ValueError as e:
        raise ValueError(str(e)) from e

    return m.AddFindingOutput(
        finding_id=result["finding_id"],
        project_id=result["project_id"],
        created_at=result["created_at"],
        deduped=result["deduped"],
        resource_uri=f"findings://{project_id}/{result['finding_id']}",
    ).model_dump(mode="json")


# ---------- Tool 3: cite ----------


@mcp.tool(
    name="cite",
    description=(
        "Attach a citation to a finding. The server fetches the URL, extracts "
        "the main content, hashes it, and stores raw HTML in blob storage for "
        "provenance. Idempotent on (finding_id, page_hash). On fetch failure "
        "the citation row is still recorded with fetch_status=0 so the trail "
        "is never lost.\n\n"
        "Example: cite(finding_id='f_...', url='https://...', excerpt='...')"
    ),
    annotations={"idempotentHint": True, "destructiveHint": False},
)
async def cite(
    finding_id: str,
    url: str,
    excerpt: str,
    ctx: Context,
) -> dict[str, Any]:
    agent = _agent_from_ctx(ctx)
    await _enforce_rate(agent.agent_id)

    f = await findings_svc.get_finding(finding_id)
    if f is None or f["agent_id"] != agent.agent_id:
        raise ValueError(f"finding {finding_id} not found for this agent")

    result = await citations_svc.cite(
        agent_id=agent.agent_id,
        finding_id=finding_id,
        url=url,
        excerpt=excerpt,
    )
    return m.CiteOutput(**result).model_dump(mode="json")


# ---------- Tool 4: query_findings ----------


@mcp.tool(
    name="query_findings",
    description=(
        "Semantic search over a project's findings. Use this to recall what "
        "has already been discovered before adding redundant findings. "
        "Cosine similarity over Voyage embeddings (truncated to 768d).\n\n"
        "Example: query_findings(project_id='p_...', semantic_query='cold start times', limit=10)"
    ),
    annotations={"readOnlyHint": True},
)
async def query_findings(
    project_id: str,
    semantic_query: str,
    ctx: Context,
    limit: int = 10,
    min_confidence: float = 0.0,
) -> dict[str, Any]:
    agent = _agent_from_ctx(ctx)
    await _enforce_rate(agent.agent_id)
    proj = await projects_svc.get_project(project_id, agent_id=agent.agent_id)
    if proj is None:
        raise ValueError(f"project {project_id} not found for this agent")
    results = await findings_svc.query_findings(
        project_id=project_id,
        semantic_query=semantic_query,
        limit=limit,
        min_confidence=min_confidence,
    )
    return m.QueryFindingsOutput(
        project_id=project_id,
        query=semantic_query,
        results=[m.QueryFindingResult(**r) for r in results],
        total=len(results),
    ).model_dump(mode="json")


# ---------- Tool 5: branch_project ----------


@mcp.tool(
    name="branch_project",
    description=(
        "Fork a project into a child investigation while keeping the parent "
        "intact. Use when you want to chase a contradiction or sub-thread "
        "without polluting the main project. Branches start clean and "
        "reference the parent through the FK.\n\n"
        "Example: branch_project(project_id='p_...', reason='contradicting cold-start claims')"
    ),
    annotations={"destructiveHint": False},
)
async def branch_project(
    project_id: str,
    reason: str,
    ctx: Context,
) -> dict[str, Any]:
    agent = _agent_from_ctx(ctx)
    await _enforce_rate(agent.agent_id)
    try:
        row = await projects_svc.branch_project(
            parent_project_id=project_id,
            agent_id=agent.agent_id,
            reason=reason,
        )
    except ValueError as e:
        raise ValueError(str(e)) from e
    return m.BranchProjectOutput(
        project_id=row["project_id"],
        parent_id=row["parent_id"],
        topic=row["topic"],
        reason=reason,
        created_at=row["created_at"],
        dashboard_url=_dashboard_url(row["project_id"]),
    ).model_dump(mode="json")


# ---------- Tool 6: request_human_review ----------


@mcp.tool(
    name="request_human_review",
    description=(
        "Pause and ask a human to review the project. The dashboard surfaces "
        "the request and (if Resend is configured) emails the owner. The "
        "project's status moves to 'review_requested' until a human approves "
        "or rejects.\n\n"
        "Example: request_human_review(project_id='p_...', reason='confidence on key claim < 0.7')"
    ),
    annotations={"destructiveHint": False},
)
async def request_human_review(
    project_id: str,
    reason: str,
    ctx: Context,
) -> dict[str, Any]:
    agent = _agent_from_ctx(ctx)
    await _enforce_rate(agent.agent_id)
    proj = await projects_svc.get_project(project_id, agent_id=agent.agent_id)
    if proj is None:
        raise ValueError(f"project {project_id} not found for this agent")
    out = await reviews_svc.request_review(
        agent_id=agent.agent_id, project_id=project_id, reason=reason
    )
    return m.RequestReviewOutput(
        review_id=out["review_id"],
        project_id=out["project_id"],
        reason=out["reason"],
        status=out["status"],
        created_at=out["created_at"],
        dashboard_url=_dashboard_url(project_id),
    ).model_dump(mode="json")


# ---------- Tool 7: publish_report ----------


@mcp.tool(
    name="publish_report",
    description=(
        "Render a structured markdown report from the project's findings + "
        "citations and publish it at a stable public URL. Confidence ≥ 0.7 "
        "are 'Confirmed'; the rest are 'Tentative'. Returns the public report URL.\n\n"
        "Example: publish_report(project_id='p_...', format='markdown')"
    ),
    annotations={"destructiveHint": False},
)
async def publish_report(
    project_id: str,
    ctx: Context,
    format: str = "markdown",
) -> dict[str, Any]:
    agent = _agent_from_ctx(ctx)
    await _enforce_rate(agent.agent_id)
    proj = await projects_svc.get_project(project_id, agent_id=agent.agent_id)
    if proj is None:
        raise ValueError(f"project {project_id} not found for this agent")
    out = await reports_svc.publish_report(
        agent_id=agent.agent_id, project_id=project_id, fmt=format
    )
    return m.PublishReportOutput(**out).model_dump(mode="json")


# ---------- Tool 8: list_projects ----------


@mcp.tool(
    name="list_projects",
    description=(
        "List the calling agent's projects, most-recent first. Returns "
        "summary rows including num_findings — useful when continuing work "
        "from a fresh session.\n\n"
        "Example: list_projects(limit=20)"
    ),
    annotations={"readOnlyHint": True},
)
async def list_projects(
    ctx: Context,
    limit: int = 20,
    status: str | None = None,
) -> dict[str, Any]:
    agent = _agent_from_ctx(ctx)
    await _enforce_rate(agent.agent_id)
    rows = await projects_svc.list_projects_for_agent(agent.agent_id, limit=limit, status=status)
    summaries = [
        m.ProjectSummary(
            project_id=r["project_id"],
            topic=r["topic"],
            depth=r["depth"],
            status=r["status"],
            num_findings=int(r["num_findings"]),
            parent_id=r["parent_id"],
            updated_at=r["updated_at"],
            created_at=r["created_at"],
        )
        for r in rows
    ]
    return m.ListProjectsOutput(projects=summaries, total=len(summaries)).model_dump(mode="json")


# ---------- ASGI mount: API key in URL path ----------


class APIKeyPathMiddleware:
    """Resolve identity for /mcp requests and forward to FastMCP.

    Two acceptable shapes:

    * ``/mcp/<api_key>[/...]`` — legacy: bcrypt-verify the key, resolve to Agent
    * ``/mcp[/...]`` with ``Authorization: Bearer <jwt>`` — OAuth: decode the JWT

    On 401 from the bearer path, we emit ``WWW-Authenticate: Bearer`` per
    RFC 9728 §5.1 so MCP clients can discover the AS automatically.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        raw_path = scope.get("path", "")
        # Outer FastAPI mount at /mcp may or may not strip the prefix
        # depending on Starlette version. Normalize either way.
        if raw_path.startswith("/mcp/"):
            inner = raw_path[len("/mcp"):]   # "/<api_key>[/...]" or "/[/...]"
        elif raw_path == "/mcp":
            inner = "/"
        else:
            inner = raw_path

        # Decide which auth path to take.
        bearer = _read_bearer_token(scope)
        if bearer is not None:
            agent = await _resolve_bearer(bearer)
            if agent is None:
                return await self._send_oauth_401(send)
            rest = inner if inner else "/"
        else:
            # Legacy URL-key path: first segment must be the key.
            if not inner or inner == "/":
                return await self._send_oauth_401(send)
            parts = inner.lstrip("/").split("/", 1)
            api_key = parts[0]
            rest = "/" + parts[1] if len(parts) > 1 else "/"
            try:
                agent = await _resolve_key(api_key)
            except Exception as e:
                return await self._send_error(
                    send, 401, f"invalid api key: {type(e).__name__}: {e}"
                )

        # FastMCP's http_app(path="/") exposes its endpoint at root.
        new_scope = dict(scope)
        new_scope["path"] = rest
        new_scope["raw_path"] = rest.encode("utf-8")
        state = dict(new_scope.get("state", {}))
        state["agent"] = agent
        new_scope["state"] = state

        await self.app(new_scope, receive, send)

    async def _send_oauth_401(self, send) -> None:
        """RFC 9728 §5.1 — point clients at the protected-resource metadata."""
        settings = get_settings()
        challenge = (
            f'Bearer realm="margin", '
            f'resource_metadata="{settings.api_base_url}/.well-known/oauth-protected-resource"'
        )
        body = json.dumps(
            {
                "error": "invalid_token",
                "error_description": "missing or invalid bearer token; see resource_metadata",
            }
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"www-authenticate", challenge.encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

    @staticmethod
    async def _send_error(send, status: int, detail: str) -> None:
        body = json.dumps({"error": detail}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


def _read_bearer_token(scope) -> str | None:
    """Extract the Bearer token from the Authorization header, if present."""
    headers = scope.get("headers") or []
    for k, v in headers:
        if k == b"authorization":
            decoded = v.decode("latin-1")
            if decoded.lower().startswith("bearer "):
                return decoded.split(" ", 1)[1].strip()
    return None


@dataclass
class _OAuthAgent(Agent):
    """An Agent reconstructed from a JWT — same shape as the bcrypt path."""


async def _resolve_bearer(token: str) -> _OAuthAgent | None:
    """Decode + validate the JWT. Returns a minimal Agent or None on failure.

    No DB lookup — agent_id and owner_id are carried in the JWT itself, and
    the tool handlers only ever read ``agent.agent_id``. Revocation works on
    the token's expiry boundary (1h); for instant kill-switch use the legacy
    path or wait for refresh-token rotation.
    """
    claims = verify_access_token(token)
    if claims is None:
        return None
    return _OAuthAgent(
        agent_id=claims["sub"],
        owner_id=claims["owner_id"],
        name="",
        key_prefix="",
    )


_inner_mcp_app = None


def get_inner_mcp_app():
    """Return the underlying FastMCP ASGI app (cached).

    Exposed so the parent FastAPI app can run ``inner.lifespan`` inside its
    own lifespan — FastMCP's streamable-http session manager initializes its
    task group there.
    """
    global _inner_mcp_app
    if _inner_mcp_app is None:
        # NOTE: stateful (default) mode is required for the Claude.ai connector
        # UI to enumerate tools — it relies on the Mcp-Session-Id header that
        # the spec issues on `initialize`. Stateless mode strips that header
        # and Claude.ai silently shows "no tools available" even though
        # tools/list responds correctly to direct POSTs (Inspector/curl work).
        # We're single-instance on Render free, so no sticky-session concern.
        _inner_mcp_app = mcp.http_app(
            transport="streamable-http", stateless_http=False, path="/"
        )
    return _inner_mcp_app


def build_mcp_app():
    """Return the ASGI app to mount at ``/mcp``.

    ``path="/"`` puts FastMCP's streamable-http endpoint at the inner-app root,
    so APIKeyPathMiddleware can forward requests after stripping the api key.
    """
    return APIKeyPathMiddleware(get_inner_mcp_app())
