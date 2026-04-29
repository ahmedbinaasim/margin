"""Citation URL canonicalization."""

from margin_api.services.citations import _normalize_url


def test_lowercases_host_and_drops_fragment():
    assert _normalize_url("HTTPS://Example.COM/Path?utm_source=tw#frag") == "https://example.com/Path"


def test_preserves_non_tracking_query():
    assert _normalize_url("https://example.com/?id=42&utm_source=x") == "https://example.com/?id=42"


def test_preserves_default_ports_implicit():
    assert _normalize_url("https://example.com:443/x") == "https://example.com/x"
    assert _normalize_url("http://example.com:80/x") == "http://example.com/x"


def test_keeps_explicit_nondefault_port():
    assert _normalize_url("http://example.com:8080/x") == "http://example.com:8080/x"
