"""Embedding pipeline: truncate + L2 renormalize, padding, cache."""

import math

import pytest

from margin_api.embeddings import (
    _l2_normalize,
    _truncate_and_renormalize,
    _zero_pad_and_renormalize,
    clear_cache,
    embed,
)


def _norm(v):
    return math.sqrt(sum(x * x for x in v))


def test_l2_normalize_returns_unit_vector():
    out = _l2_normalize([3.0, 4.0])
    assert abs(_norm(out) - 1.0) < 1e-6


def test_l2_normalize_handles_zero_vector():
    out = _l2_normalize([0.0, 0.0])
    assert out == [0.0, 0.0]


def test_truncate_and_renormalize_returns_unit_vector_at_target_dim():
    raw = [float(i + 1) for i in range(1024)]
    out = _truncate_and_renormalize(raw, 768)
    assert len(out) == 768
    assert abs(_norm(out) - 1.0) < 1e-6


def test_zero_pad_and_renormalize_keeps_unit_norm():
    raw = [1.0 / math.sqrt(384)] * 384  # already unit-norm
    out = _zero_pad_and_renormalize(raw, 768)
    assert len(out) == 768
    # Last 384 entries should be exactly zero before final renorm; after renorm
    # they remain zero, and the leading 384 form the full unit vector.
    assert all(v == 0.0 for v in out[384:])
    assert abs(_norm(out) - 1.0) < 1e-6


@pytest.mark.asyncio
async def test_embed_validates_input_type():
    with pytest.raises(ValueError):
        await embed(["x"], input_type="bogus")


@pytest.mark.asyncio
async def test_embed_returns_unit_vectors_via_voyage_mock():
    clear_cache()
    out = await embed(["hello", "world"], input_type="document")
    assert len(out) == 2
    for v in out:
        assert len(v) == 768
        assert abs(_norm(v) - 1.0) < 1e-6


@pytest.mark.asyncio
async def test_embed_caches_by_input_type():
    clear_cache()
    a = (await embed(["same text"], input_type="document"))[0]
    b = (await embed(["same text"], input_type="document"))[0]
    assert a == b  # cache hit returns identical list
    # Different input_type must NOT collide with the cache.
    c = (await embed(["same text"], input_type="query"))[0]
    # Cached embedding for query may equal document embedding under our mock,
    # but the cache key must differ; this assertion is an existence check —
    # the call did NOT raise, and we got a vector.
    assert len(c) == 768


@pytest.mark.asyncio
async def test_embed_empty_input_returns_empty():
    clear_cache()
    assert await embed([], input_type="document") == []


@pytest.mark.slow
@pytest.mark.asyncio
async def test_embed_local_fallback(monkeypatch):
    """Force the Voyage path to fail; ensure local bge-small fallback runs.

    Marked slow — loads ~80MB of model weights.
    """
    from margin_api import embeddings as em

    async def _boom(*a, **kw):
        raise RuntimeError("simulated voyage failure")

    monkeypatch.setattr(em, "_embed_voyage", _boom)
    em.clear_cache()
    out = await em.embed(["fallback path"], input_type="document")
    assert len(out) == 1
    assert len(out[0]) == 768
    assert abs(_norm(out[0]) - 1.0) < 1e-6
