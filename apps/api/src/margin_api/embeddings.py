"""Voyage 3.5-lite primary, local bge-small fallback. Always returns 768d unit vectors.

This is the canonical implementation referenced from SPEC §9. ``add_finding``
should pass ``input_type="document"``; ``query_findings`` should pass
``"query"``. Voyage uses these hints to specialize representations.

The local fallback uses ``BAAI/bge-small-en-v1.5`` (384d), zero-padded to
EMBED_DIM and L2-renormalized. The padding preserves the column dim so the
HNSW index doesn't need to be rebuilt; quality drops, but the system stays
queryable through a Voyage outage.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
from collections.abc import Sequence

from .config import get_settings

_voyage_client = None
_local_model = None
_embed_cache: dict[str, list[float]] = {}
_CACHE_LIMIT = 2048


def _l2_normalize(vec: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in vec))
    if n == 0:
        return vec
    return [x / n for x in vec]


def _truncate_and_renormalize(vec: list[float], target_dim: int) -> list[float]:
    return _l2_normalize(list(vec[:target_dim]))


def _zero_pad_and_renormalize(vec: list[float], target_dim: int) -> list[float]:
    if len(vec) >= target_dim:
        return _truncate_and_renormalize(vec, target_dim)
    padded = list(vec) + [0.0] * (target_dim - len(vec))
    return _l2_normalize(padded)


def _cache_key(text: str, input_type: str) -> str:
    return hashlib.sha256(f"{input_type}\x00{text}".encode()).hexdigest()


def _get_voyage_client():
    global _voyage_client
    if _voyage_client is None:
        import voyageai

        settings = get_settings()
        if not settings.voyage_api_key:
            raise RuntimeError("voyage_api_key not configured")
        _voyage_client = voyageai.AsyncClient(api_key=settings.voyage_api_key)
    return _voyage_client


def _ensure_local_model():
    global _local_model
    if _local_model is None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise RuntimeError(
                "Local embedding fallback requires `sentence-transformers`. "
                "Install with: uv sync --extra fallback"
            ) from e
        _local_model = SentenceTransformer("BAAI/bge-small-en-v1.5")
    return _local_model


async def _embed_voyage(texts: Sequence[str], input_type: str) -> list[list[float]]:
    settings = get_settings()
    client = _get_voyage_client()
    resp = await client.embed(
        texts=list(texts),
        model=settings.voyage_embed_model,
        input_type=input_type,
    )
    return [_truncate_and_renormalize(e, settings.embed_dim) for e in resp.embeddings]


async def _embed_local(texts: Sequence[str]) -> list[list[float]]:
    settings = get_settings()
    model = _ensure_local_model()
    raw = await asyncio.to_thread(
        model.encode, list(texts), normalize_embeddings=True, show_progress_bar=False
    )
    return [_zero_pad_and_renormalize(list(v), settings.embed_dim) for v in raw.tolist()]


async def embed(
    texts: Sequence[str], input_type: str = "document"
) -> list[list[float]]:
    """Primary: Voyage. Fallback (any exception): local bge-small. 768d unit vectors."""

    if not texts:
        return []
    if input_type not in ("document", "query"):
        raise ValueError("input_type must be 'document' or 'query'")

    # Cache lookup
    keys = [_cache_key(t, input_type) for t in texts]
    cached: list[list[float] | None] = [_embed_cache.get(k) for k in keys]
    todo = [(i, t) for i, (t, c) in enumerate(zip(texts, cached, strict=True)) if c is None]
    if todo:
        try:
            new_vecs = await _embed_voyage([t for _, t in todo], input_type)
        except Exception:
            new_vecs = await _embed_local([t for _, t in todo])
        for (i, _), v in zip(todo, new_vecs, strict=True):
            cached[i] = v
            _embed_cache[keys[i]] = v

    # Trim cache (LRU-ish: just drop arbitrary entries when over limit)
    if len(_embed_cache) > _CACHE_LIMIT:
        for k in list(_embed_cache.keys())[: len(_embed_cache) - _CACHE_LIMIT]:
            _embed_cache.pop(k, None)

    return [v for v in cached if v is not None]


def clear_cache() -> None:
    """For tests."""
    _embed_cache.clear()
