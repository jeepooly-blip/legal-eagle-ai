"""TTL cache for retrieval results."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Hashable, Optional


@dataclass
class _Entry:
    value: Any
    expires_at: float


class TTLCache:
    def __init__(self, ttl_seconds: int = 900) -> None:
        self.ttl = ttl_seconds
        self._data: dict[Hashable, _Entry] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: Hashable) -> Optional[Any]:
        async with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            if entry.expires_at < time.time():
                self._data.pop(key, None)
                return None
            return entry.value

    async def set(self, key: Hashable, value: Any, ttl: Optional[int] = None) -> None:
        async with self._lock:
            self._data[key] = _Entry(
                value=value, expires_at=time.time() + (ttl or self.ttl)
            )

    async def clear(self) -> None:
        async with self._lock:
            self._data.clear()
