"""Middleware package."""

from .cache import TTLCache
from .normalizer import dedupe, rank
from .provenance import ProvenanceRecord, ProvenanceTracker
from .query_router import detect_jurisdictions, route
from .rate_limiter import RateLimiter

__all__ = [
    "TTLCache",
    "ProvenanceRecord",
    "ProvenanceTracker",
    "RateLimiter",
    "detect_jurisdictions",
    "route",
    "dedupe",
    "rank",
]
