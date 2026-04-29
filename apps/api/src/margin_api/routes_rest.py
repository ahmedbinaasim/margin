"""REST router. SPEC §4.2.

Endpoints:
    POST   /v1/projects                       → start_research
    POST   /v1/projects/{id}/findings         → add_finding
    POST   /v1/findings/{id}/citations        → cite
    POST   /v1/projects/{id}/query            → query_findings
    POST   /v1/projects/{id}/branches         → branch_project
    POST   /v1/projects/{id}/reviews          → request_human_review
    POST   /v1/projects/{id}/reports          → publish_report
    GET    /v1/projects                       → list_projects
    GET    /v1/reports/{slug}                 → public report fetch
    GET    /v1/events                         → SSE stream (dashboard)
    GET    /v1/events/recent                  → polling fallback

Dashboard auth (separate JWT scope, not API-key auth):
    POST /v1/auth/request, POST /v1/auth/verify
    POST /v1/agents, GET /v1/agents
    GET  /v1/me
    POST /v1/reviews/{review_id}/decide
"""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from . import models as m
from .auth import (
    AgentDep,
    OwnerDep,
    decode_owner_token,
    issue_owner_token,
)
from .config import get_settings
from .rate_limit import check as rate_check
from .services import (
    agents as agents_svc,
)
from .services import (
    auth_codes as auth_codes_svc,
)
from .services import (
    citations as citations_svc,
)
from .services import (
    events as events_svc,
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

router = APIRouter(prefix="/v1")


def _dashboard_url(project_id: str) -> str:
    return f"{get_settings().public_base_url}/app/p/{project_id}"


async def _enforce_rate(agent_id: str) -> None:
    if not await rate_check(agent_id):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="rate limited")


# ---------- Auth (dashboard, owner-scoped JWT) ----------


@router.post("/auth/request", response_model=m.AuthRequestOutput)
async def auth_request(body: m.AuthRequestInput) -> m.AuthRequestOutput:
    code, sent = await auth_codes_svc.request_code(body.email)
    settings = get_settings()
    if settings.resend_api_key and sent:
        return m.AuthRequestOutput(sent=True, dev_code=None)
    # Dev mode: return the code in the response for testability.
    return m.AuthRequestOutput(sent=False, dev_code=code)


@router.post("/auth/verify", response_model=m.AuthVerifyOutput)
async def auth_verify(body: m.AuthVerifyInput) -> m.AuthVerifyOutput:
    owner_id = await auth_codes_svc.verify_code(body.email, body.code)
    if owner_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or expired code")
    token = issue_owner_token(owner_id, body.email)
    return m.AuthVerifyOutput(token=token, owner_id=owner_id)


@router.get("/me")
async def me(owner: OwnerDep) -> dict:
    return {"owner_id": owner.owner_id, "email": owner.email}


@router.post("/agents", response_model=m.CreateAgentOutput)
async def create_agent(body: m.CreateAgentInput, owner: OwnerDep) -> m.CreateAgentOutput:
    row, plaintext = await agents_svc.create_agent_for_owner(owner.owner_id, body.name)
    settings = get_settings()
    return m.CreateAgentOutput(
        agent_id=row["agent_id"],
        name=row["name"],
        api_key=plaintext,
        key_prefix=row["key_prefix"],
        mcp_url=f"{settings.api_base_url}/mcp/{plaintext}",
    )


@router.get("/agents", response_model=list[m.AgentSummary])
async def list_agents(owner: OwnerDep) -> list[m.AgentSummary]:
    rows = await agents_svc.list_agents_for_owner(owner.owner_id)
    return [m.AgentSummary(**r) for r in rows]


# ---------- Eight primitives (agent-keyed) ----------


@router.post("/projects", response_model=m.StartResearchOutput, status_code=status.HTTP_201_CREATED)
async def start_research(body: m.StartResearchInput, agent: AgentDep) -> m.StartResearchOutput:
    await _enforce_rate(agent.agent_id)
    row = await projects_svc.create_project(
        agent_id=agent.agent_id,
        topic=body.topic,
        depth=body.depth,
        deadline=body.deadline,
    )
    return m.StartResearchOutput(
        project_id=row["project_id"],
        topic=row["topic"],
        depth=row["depth"],
        deadline=row["deadline"],
        created_at=row["created_at"],
        dashboard_url=_dashboard_url(row["project_id"]),
    )


@router.get("/projects", response_model=m.ListProjectsOutput)
async def list_projects(
    agent: AgentDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
) -> m.ListProjectsOutput:
    await _enforce_rate(agent.agent_id)
    rows = await projects_svc.list_projects_for_agent(agent.agent_id, limit=limit, status=status_filter)
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
    return m.ListProjectsOutput(projects=summaries, total=len(summaries))


def _own_project_or_404(project_id: str, agent_id: str):
    async def _check():
        row = await projects_svc.get_project(project_id, agent_id=agent_id)
        if row is None:
            raise HTTPException(status_code=404, detail="project not found")
        return row

    return _check


@router.post(
    "/projects/{project_id}/findings",
    response_model=m.AddFindingOutput,
    status_code=status.HTTP_201_CREATED,
)
async def add_finding(
    project_id: str, body: m.AddFindingInput, agent: AgentDep
) -> m.AddFindingOutput:
    await _enforce_rate(agent.agent_id)
    row = await projects_svc.get_project(project_id, agent_id=agent.agent_id)
    if row is None:
        raise HTTPException(status_code=404, detail="project not found")
    try:
        result = await findings_svc.add_finding(
            agent_id=agent.agent_id,
            project_id=project_id,
            claim=body.claim,
            evidence=body.evidence,
            source=str(body.source) if body.source else None,
            confidence=body.confidence,
            contradicts=body.contradicts,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return m.AddFindingOutput(
        finding_id=result["finding_id"],
        project_id=result["project_id"],
        created_at=result["created_at"],
        deduped=result["deduped"],
        resource_uri=f"findings://{project_id}/{result['finding_id']}",
    )


@router.post(
    "/findings/{finding_id}/citations",
    response_model=m.CiteOutput,
    status_code=status.HTTP_201_CREATED,
)
async def cite(finding_id: str, body: m.CiteInput, agent: AgentDep) -> m.CiteOutput:
    await _enforce_rate(agent.agent_id)
    f = await findings_svc.get_finding(finding_id)
    if f is None or f["agent_id"] != agent.agent_id:
        raise HTTPException(status_code=404, detail="finding not found")
    result = await citations_svc.cite(
        agent_id=agent.agent_id,
        finding_id=finding_id,
        url=str(body.url),
        excerpt=body.excerpt,
    )
    return m.CiteOutput(**result)


@router.post("/projects/{project_id}/query", response_model=m.QueryFindingsOutput)
async def query_findings(
    project_id: str, body: m.QueryFindingsInput, agent: AgentDep
) -> m.QueryFindingsOutput:
    await _enforce_rate(agent.agent_id)
    row = await projects_svc.get_project(project_id, agent_id=agent.agent_id)
    if row is None:
        raise HTTPException(status_code=404, detail="project not found")
    results = await findings_svc.query_findings(
        project_id=project_id,
        semantic_query=body.semantic_query,
        limit=body.limit,
        min_confidence=body.min_confidence,
    )
    return m.QueryFindingsOutput(
        project_id=project_id,
        query=body.semantic_query,
        results=[m.QueryFindingResult(**r) for r in results],
        total=len(results),
    )


@router.post(
    "/projects/{project_id}/branches",
    response_model=m.BranchProjectOutput,
    status_code=status.HTTP_201_CREATED,
)
async def branch_project(
    project_id: str, body: m.BranchProjectInput, agent: AgentDep
) -> m.BranchProjectOutput:
    await _enforce_rate(agent.agent_id)
    try:
        row = await projects_svc.branch_project(
            parent_project_id=project_id,
            agent_id=agent.agent_id,
            reason=body.reason,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail="project not found") from e
    return m.BranchProjectOutput(
        project_id=row["project_id"],
        parent_id=row["parent_id"],
        topic=row["topic"],
        reason=body.reason,
        created_at=row["created_at"],
        dashboard_url=_dashboard_url(row["project_id"]),
    )


@router.post(
    "/projects/{project_id}/reviews",
    response_model=m.RequestReviewOutput,
    status_code=status.HTTP_201_CREATED,
)
async def request_review(
    project_id: str, body: m.RequestReviewInput, agent: AgentDep
) -> m.RequestReviewOutput:
    await _enforce_rate(agent.agent_id)
    row = await projects_svc.get_project(project_id, agent_id=agent.agent_id)
    if row is None:
        raise HTTPException(status_code=404, detail="project not found")
    out = await reviews_svc.request_review(
        agent_id=agent.agent_id, project_id=project_id, reason=body.reason
    )
    return m.RequestReviewOutput(
        review_id=out["review_id"],
        project_id=out["project_id"],
        reason=out["reason"],
        status=out["status"],
        created_at=out["created_at"],
        dashboard_url=_dashboard_url(project_id),
    )


@router.post(
    "/projects/{project_id}/reports",
    response_model=m.PublishReportOutput,
    status_code=status.HTTP_201_CREATED,
)
async def publish_report(
    project_id: str, body: m.PublishReportInput, agent: AgentDep
) -> m.PublishReportOutput:
    await _enforce_rate(agent.agent_id)
    row = await projects_svc.get_project(project_id, agent_id=agent.agent_id)
    if row is None:
        raise HTTPException(status_code=404, detail="project not found")
    out = await reports_svc.publish_report(
        agent_id=agent.agent_id, project_id=project_id, fmt=body.format
    )
    return m.PublishReportOutput(**out)


# ---------- Public (no auth) ----------


@router.get("/reports/{slug}", response_model=m.ReportPublicOutput)
async def get_report(slug: str) -> m.ReportPublicOutput:
    row = await reports_svc.get_report_by_slug(slug)
    if row is None:
        raise HTTPException(status_code=404, detail="report not found")
    return m.ReportPublicOutput(
        report_id=row["report_id"],
        project_id=row["project_id"],
        format=row["format"],
        public_slug=row["public_slug"],
        body=row["body"],
        created_at=row["created_at"],
    )


# ---------- Reviews dashboard decision ----------


class ReviewDecisionInput(BaseModel):
    decision: str
    note: str | None = None


@router.post("/reviews/{review_id}/decide")
async def decide_review(review_id: str, body: ReviewDecisionInput, owner: OwnerDep) -> dict:
    row = await reviews_svc.decide(review_id, body.decision, body.note)
    if row is None:
        raise HTTPException(status_code=404, detail="review not found or already decided")
    return {"review_id": row["review_id"], "status": row["status"]}


# ---------- Events (SSE + recent) ----------


@router.get("/events/recent")
async def events_recent(
    request: Request,
    token: Annotated[str | None, Query()] = None,
    agent_token: Annotated[str | None, Query(alias="agent_key")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
):
    """Polling fallback for the dashboard. Auth: either a JWT (?token=) or an API key (?agent_key=)."""
    agent_id = await _resolve_events_auth(request, token, agent_token)
    return await events_svc.list_recent(agent_id, limit=limit)


@router.get("/events")
async def events_stream(
    request: Request,
    token: Annotated[str | None, Query()] = None,
    agent_token: Annotated[str | None, Query(alias="agent_key")] = None,
    since: Annotated[int | None, Query()] = None,
):
    agent_id = await _resolve_events_auth(request, token, agent_token)

    async def gen():
        async for event in events_svc.subscribe(agent_id, since=since):
            yield {"event": event["kind"], "data": json.dumps(event)}

    return EventSourceResponse(gen())


async def _resolve_events_auth(request: Request, jwt_token: str | None, agent_key: str | None) -> str:
    """Accept either an owner JWT (which lists all agents under that owner) — for
    now we resolve it to the FIRST agent for the owner; the dashboard typically
    has only one — or an API key directly. This is intentionally simple."""
    if agent_key:
        from .auth import _resolve_key  # type: ignore

        agent = await _resolve_key(agent_key)
        return agent.agent_id
    if jwt_token:
        owner = decode_owner_token(jwt_token)
        rows = await agents_svc.list_agents_for_owner(owner.owner_id)
        if not rows:
            raise HTTPException(status_code=404, detail="no agents for owner")
        return rows[0]["agent_id"]

    # Fallback: also accept Authorization: Bearer
    auth = request.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        from .auth import _resolve_key  # type: ignore

        token = auth.split(" ", 1)[1].strip()
        agent = await _resolve_key(token)
        return agent.agent_id
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="provide ?token=, ?agent_key=, or Authorization header")
