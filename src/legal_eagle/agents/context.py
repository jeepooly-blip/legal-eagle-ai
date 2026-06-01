"""Shared agent state: a per-session context with all middleware + LLM."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..llm.client import LLMClient
from ..middleware.cache import TTLCache
from ..middleware.provenance import ProvenanceTracker
from ..middleware.rate_limiter import RateLimiter


@dataclass
class AgentContext:
    session_id: str
    llm: LLMClient
    provenance: ProvenanceTracker
    cache: TTLCache
    rate_limiter: RateLimiter
    metadata: dict = field(default_factory=dict)
