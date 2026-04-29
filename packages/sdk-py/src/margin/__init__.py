"""Margin Python SDK — typed wrapper over the REST API.

Both sync (:class:`Margin`) and async (:class:`AsyncMargin`) clients are
provided; they share methods, return values are plain dicts (the API's
JSON shape).
"""

from __future__ import annotations

from typing import Any

import httpx


__version__ = "0.1.0"


class MarginError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(f"{status}: {detail}")
        self.status = status
        self.detail = detail


_DEFAULT_BASE = "https://api.margin.dev"


def _raise(resp: httpx.Response) -> None:
    if resp.is_success:
        return
    try:
        body = resp.json()
        detail = body.get("detail") or str(body)
    except Exception:
        detail = resp.text or resp.reason_phrase
    raise MarginError(resp.status_code, str(detail))


class Margin:
    """Synchronous client. Each method maps 1:1 to a REST primitive."""

    def __init__(
        self,
        api_key: str,
        base_url: str = _DEFAULT_BASE,
        timeout: float = 30.0,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url,
            timeout=timeout,
            headers={"Authorization": f"Bearer {api_key}"},
        )

    def __enter__(self) -> "Margin":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    # --- Primitives ---

    def start_research(
        self, topic: str, depth: str = "standard", deadline: str | None = None
    ) -> dict[str, Any]:
        resp = self._client.post(
            "/v1/projects",
            json={"topic": topic, "depth": depth, "deadline": deadline},
        )
        _raise(resp)
        return resp.json()

    def list_projects(
        self, limit: int = 20, status: str | None = None
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        resp = self._client.get("/v1/projects", params=params)
        _raise(resp)
        return resp.json()

    def add_finding(
        self,
        project_id: str,
        claim: str,
        evidence: str,
        confidence: float,
        source: str | None = None,
        contradicts: str | None = None,
    ) -> dict[str, Any]:
        body = {
            "claim": claim,
            "evidence": evidence,
            "confidence": confidence,
            "source": source,
            "contradicts": contradicts,
        }
        resp = self._client.post(f"/v1/projects/{project_id}/findings", json=body)
        _raise(resp)
        return resp.json()

    def cite(self, finding_id: str, url: str, excerpt: str) -> dict[str, Any]:
        resp = self._client.post(
            f"/v1/findings/{finding_id}/citations",
            json={"url": url, "excerpt": excerpt},
        )
        _raise(resp)
        return resp.json()

    def query_findings(
        self,
        project_id: str,
        semantic_query: str,
        limit: int = 10,
        min_confidence: float = 0.0,
    ) -> dict[str, Any]:
        resp = self._client.post(
            f"/v1/projects/{project_id}/query",
            json={
                "semantic_query": semantic_query,
                "limit": limit,
                "min_confidence": min_confidence,
            },
        )
        _raise(resp)
        return resp.json()

    def branch_project(self, project_id: str, reason: str) -> dict[str, Any]:
        resp = self._client.post(
            f"/v1/projects/{project_id}/branches",
            json={"reason": reason},
        )
        _raise(resp)
        return resp.json()

    def request_human_review(self, project_id: str, reason: str) -> dict[str, Any]:
        resp = self._client.post(
            f"/v1/projects/{project_id}/reviews",
            json={"reason": reason},
        )
        _raise(resp)
        return resp.json()

    def publish_report(
        self, project_id: str, format: str = "markdown"
    ) -> dict[str, Any]:
        resp = self._client.post(
            f"/v1/projects/{project_id}/reports",
            json={"format": format},
        )
        _raise(resp)
        return resp.json()


class AsyncMargin:
    """Async variant. Same methods; awaitable."""

    def __init__(
        self,
        api_key: str,
        base_url: str = _DEFAULT_BASE,
        timeout: float = 30.0,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            headers={"Authorization": f"Bearer {api_key}"},
        )

    async def __aenter__(self) -> "AsyncMargin":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    async def start_research(
        self, topic: str, depth: str = "standard", deadline: str | None = None
    ) -> dict[str, Any]:
        resp = await self._client.post(
            "/v1/projects",
            json={"topic": topic, "depth": depth, "deadline": deadline},
        )
        _raise(resp)
        return resp.json()

    async def list_projects(
        self, limit: int = 20, status: str | None = None
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        resp = await self._client.get("/v1/projects", params=params)
        _raise(resp)
        return resp.json()

    async def add_finding(
        self,
        project_id: str,
        claim: str,
        evidence: str,
        confidence: float,
        source: str | None = None,
        contradicts: str | None = None,
    ) -> dict[str, Any]:
        body = {
            "claim": claim,
            "evidence": evidence,
            "confidence": confidence,
            "source": source,
            "contradicts": contradicts,
        }
        resp = await self._client.post(
            f"/v1/projects/{project_id}/findings", json=body
        )
        _raise(resp)
        return resp.json()

    async def cite(self, finding_id: str, url: str, excerpt: str) -> dict[str, Any]:
        resp = await self._client.post(
            f"/v1/findings/{finding_id}/citations",
            json={"url": url, "excerpt": excerpt},
        )
        _raise(resp)
        return resp.json()

    async def query_findings(
        self,
        project_id: str,
        semantic_query: str,
        limit: int = 10,
        min_confidence: float = 0.0,
    ) -> dict[str, Any]:
        resp = await self._client.post(
            f"/v1/projects/{project_id}/query",
            json={
                "semantic_query": semantic_query,
                "limit": limit,
                "min_confidence": min_confidence,
            },
        )
        _raise(resp)
        return resp.json()

    async def branch_project(self, project_id: str, reason: str) -> dict[str, Any]:
        resp = await self._client.post(
            f"/v1/projects/{project_id}/branches",
            json={"reason": reason},
        )
        _raise(resp)
        return resp.json()

    async def request_human_review(
        self, project_id: str, reason: str
    ) -> dict[str, Any]:
        resp = await self._client.post(
            f"/v1/projects/{project_id}/reviews",
            json={"reason": reason},
        )
        _raise(resp)
        return resp.json()

    async def publish_report(
        self, project_id: str, format: str = "markdown"
    ) -> dict[str, Any]:
        resp = await self._client.post(
            f"/v1/projects/{project_id}/reports",
            json={"format": format},
        )
        _raise(resp)
        return resp.json()


__all__ = ["Margin", "AsyncMargin", "MarginError"]
