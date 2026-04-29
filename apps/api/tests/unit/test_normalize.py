"""Hashing + normalization invariants used by add_finding."""

from margin_api.services.findings import _content_hash, _vec_to_pgvector


def test_content_hash_is_deterministic():
    a = _content_hash("Hello world", "Evidence quote")
    b = _content_hash("Hello world", "Evidence quote")
    assert a == b


def test_content_hash_separates_claim_from_evidence():
    # A single-string concat where (claim, evidence) collide should NOT collide.
    a = _content_hash("ab", "c")
    b = _content_hash("a", "bc")
    assert a != b


def test_content_hash_normalizes_whitespace_and_case():
    a = _content_hash("Hello World", "Foo Bar")
    b = _content_hash("hello world  ", "  FOO BAR")
    assert a == b


def test_vec_pgvector_format():
    v = [0.1, -0.2, 0.0]
    s = _vec_to_pgvector(v)
    assert s.startswith("[")
    assert s.endswith("]")
    parts = s[1:-1].split(",")
    assert len(parts) == 3
