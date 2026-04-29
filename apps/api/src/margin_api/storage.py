"""Cloudflare R2 (S3-compatible) blob storage for raw HTML provenance.

Boto3 is sync, so call methods are wrapped in :func:`asyncio.to_thread`.
When R2 is not configured, :data:`r2_enabled` is False and call sites should
record ``r2_key=NULL`` and ``fetch_status=0``.
"""

from __future__ import annotations

import asyncio
from functools import lru_cache

from .config import get_settings


@lru_cache(maxsize=1)
def _client():
    settings = get_settings()
    if not settings.r2_enabled:
        raise RuntimeError("R2 not configured")
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=settings.r2_endpoint,
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        region_name="auto",
        config=Config(signature_version="s3v4"),
    )


def is_enabled() -> bool:
    return get_settings().r2_enabled


async def put_html(key: str, html_bytes: bytes) -> None:
    """Upload raw HTML to R2. Raises on failure; callers should catch."""
    settings = get_settings()
    client = _client()
    await asyncio.to_thread(
        client.put_object,
        Bucket=settings.r2_bucket,
        Key=key,
        Body=html_bytes,
        ContentType="text/html; charset=utf-8",
    )


async def signed_get(key: str, ttl: int = 604800) -> str:
    """Pre-signed GET URL; default 7-day TTL."""
    settings = get_settings()
    client = _client()
    return await asyncio.to_thread(
        client.generate_presigned_url,
        "get_object",
        Params={"Bucket": settings.r2_bucket, "Key": key},
        ExpiresIn=ttl,
    )
