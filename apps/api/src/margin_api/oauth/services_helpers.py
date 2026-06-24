"""Tiny utility kept separate from services.py to avoid circular imports."""

from __future__ import annotations

import hashlib


def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()
