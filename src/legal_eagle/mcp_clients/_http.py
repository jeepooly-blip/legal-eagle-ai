"""Shared HTTP client helpers used by the MCP clients."""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)


class HTTPError(Exception):
    pass


@retry(
    retry=retry_if_exception_type((httpx.HTTPError, HTTPError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)
async def get_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: Optional[dict[str, Any]] = None,
    headers: Optional[dict[str, str]] = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    resp = await client.get(url, params=params, headers=headers, timeout=timeout)
    if resp.status_code >= 400:
        raise HTTPError(f"GET {url} -> {resp.status_code}: {resp.text[:200]}")
    try:
        return resp.json()
    except Exception as e:  # noqa: BLE001
        raise HTTPError(f"Non-JSON response from {url}: {e}") from e
