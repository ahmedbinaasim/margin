"""Pydantic I/O models for the eight tools and supporting endpoints.

These mirror SPEC §4.1. Both REST routes and MCP tools use them.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

# ----- start_research -----


class StartResearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str = Field(min_length=4, max_length=500, description="The question or thesis.")
    depth: Literal["quick", "standard", "thorough"] = Field(
        default="standard",
        description="Controls how aggressively the agent should pursue contradictions and breadth.",
    )
    deadline: datetime | None = Field(
        default=None,
        description="Soft deadline; surfaced on the dashboard.",
    )


class StartResearchOutput(BaseModel):
    project_id: str
    topic: str
    depth: str
    deadline: datetime | None
    created_at: datetime
    dashboard_url: str


# ----- add_finding -----


class AddFindingInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim: str = Field(min_length=4, max_length=500)
    evidence: str = Field(min_length=4, max_length=4000)
    source: HttpUrl | None = Field(default=None, description="Strongly recommended.")
    confidence: float = Field(ge=0, le=1)
    contradicts: str | None = None


class AddFindingOutput(BaseModel):
    finding_id: str
    project_id: str
    created_at: datetime
    deduped: bool
    resource_uri: str


# ----- cite -----


class CiteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: HttpUrl
    excerpt: str = Field(min_length=1, max_length=4000)


class CiteOutput(BaseModel):
    citation_id: str
    finding_id: str
    page_hash: str
    fetched_at: datetime | None
    fetch_status: int
    archive_url: str | None = None


# ----- query_findings -----


class QueryFindingsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    semantic_query: str = Field(min_length=2, max_length=500)
    limit: int = Field(default=10, ge=1, le=50)
    min_confidence: float = Field(default=0.0, ge=0, le=1)


class QueryFindingResult(BaseModel):
    finding_id: str
    claim: str
    evidence_excerpt: str
    source_url: str | None
    confidence: float
    similarity: float


class QueryFindingsOutput(BaseModel):
    project_id: str
    query: str
    results: list[QueryFindingResult]
    total: int


# ----- branch_project -----


class BranchProjectInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=4, max_length=500)


class BranchProjectOutput(BaseModel):
    project_id: str
    parent_id: str
    topic: str
    reason: str
    created_at: datetime
    dashboard_url: str


# ----- request_human_review -----


class RequestReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=4, max_length=500)


class RequestReviewOutput(BaseModel):
    review_id: str
    project_id: str
    reason: str
    status: Literal["pending", "approved", "rejected"]
    created_at: datetime
    dashboard_url: str


# ----- publish_report -----


class PublishReportInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: Literal["markdown", "html", "json"] = "markdown"


class PublishReportOutput(BaseModel):
    report_id: str
    project_id: str
    format: str
    public_slug: str
    report_url: str
    created_at: datetime


# ----- list_projects -----


class ProjectSummary(BaseModel):
    project_id: str
    topic: str
    depth: str
    status: str
    num_findings: int
    parent_id: str | None
    updated_at: datetime
    created_at: datetime


class ListProjectsOutput(BaseModel):
    projects: list[ProjectSummary]
    total: int


# ----- Auth (dashboard) -----


class AuthRequestInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)


class AuthRequestOutput(BaseModel):
    sent: bool
    dev_code: str | None = None  # only set when RESEND_API_KEY is unset (dev mode)


class AuthVerifyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    code: str = Field(min_length=6, max_length=6)


class AuthVerifyOutput(BaseModel):
    token: str
    owner_id: str


class CreateAgentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)


class CreateAgentOutput(BaseModel):
    agent_id: str
    name: str
    api_key: str  # plaintext, returned ONCE
    key_prefix: str
    mcp_url: str


class AgentSummary(BaseModel):
    agent_id: str
    name: str
    key_prefix: str
    last_used_at: datetime | None
    created_at: datetime


# ----- Reports public -----


class ReportPublicOutput(BaseModel):
    report_id: str
    project_id: str
    format: str
    public_slug: str
    body: str
    created_at: datetime
