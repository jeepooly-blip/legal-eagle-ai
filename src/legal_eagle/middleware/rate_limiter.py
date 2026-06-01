"""Token-bucket rate limiter.

Async-safe with a single lock per bucket. Defaults to per-process.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field


@dataclass
class _Bucket:
    capacity: float
    refill_per_sec: float
    tokens: float = field(init=False)
    last: float = field(init=False)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def __post_init__(self) -> None:
        self.tokens = self.capacity
        self.last = time.monotonic()

    async def acquire(self, n: float = 1.0) -> None:
        async with self.lock:
            now = time.monotonic()
            elapsed = now - self.last
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_sec)
            self.last = now
            if self.tokens >= n:
                self.tokens -= n
                return
            # Sleep until refill
            wait = (n - self.tokens) / self.refill_per_sec
            await asyncio.sleep(wait)
            self.tokens = max(0.0, self.tokens + wait * self.refill_per_sec - n)
            self.last = time.monotonic()


class RateLimiter:
    """One bucket per namespace key."""

    def __init__(self, rpm: int = 30) -> None:
        self._rpm = max(1, rpm)
        self._buckets: dict[str, _Bucket] = {}
        self._global_lock = asyncio.Lock()

    async def acquire(self, key: str = "default", n: float = 1.0) -> None:
        b = self._buckets.get(key)
        if b is None:
            async with self._global_lock:
                b = self._buckets.setdefault(
                    key,
                    _Bucket(
                        capacity=self._rpm,
                        refill_per_sec=self._rpm / 60.0,
                    ),
                )
        await b.acquire(n)
