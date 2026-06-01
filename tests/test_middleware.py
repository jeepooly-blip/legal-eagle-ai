"""Unit tests for the cache and rate limiter."""

import asyncio

import pytest

from legal_eagle.middleware.cache import TTLCache
from legal_eagle.middleware.rate_limiter import RateLimiter


@pytest.mark.asyncio
async def test_cache_set_get() -> None:
    c = TTLCache(ttl_seconds=10)
    await c.set("k", {"a": 1})
    v = await c.get("k")
    assert v == {"a": 1}


@pytest.mark.asyncio
async def test_cache_ttl_expiry() -> None:
    c = TTLCache(ttl_seconds=0)  # immediately expired
    await c.set("k", 42)
    await asyncio.sleep(0.05)
    assert await c.get("k") is None


@pytest.mark.asyncio
async def test_rate_limiter_acquires() -> None:
    rl = RateLimiter(rpm=6000)  # very high so it doesn't block
    await rl.acquire("test", n=1)
    await rl.acquire("test", n=1)
