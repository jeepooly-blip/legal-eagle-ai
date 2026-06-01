"""US Retriever — wraps CourtListener with cache + provenance."""

from __future__ import annotations

import logging

from ..mcp_clients import CourtListenerClient
from ..schemas.legal_document import DocumentBundle
from ..schemas.task_handoff import ResearchTask
from .context import AgentContext

logger = logging.getLogger(__name__)


class USRetriever:
    async def run(self, task: ResearchTask, ctx: AgentContext) -> DocumentBundle:
        cache_key = ("us", task.query, tuple(sorted((task.filters or {}).items())))
        cached = await ctx.cache.get(cache_key)
        if cached is not None:
            return cached
        filters = task.filters or {}
        async with CourtListenerClient() as cl:
            bundle = await cl.search_opinions(
                task.query,
                court=filters.get("court"),
                date_after=filters.get("date_after"),
                date_before=filters.get("date_before"),
                max_results=task.max_results,
            )
        ctx.provenance.record(
            session_id=task.parent_session_id,
            jurisdiction="us",
            source="courtlistener",
            query=task.query,
            documents_returned=len(bundle.documents),
            extra={"task_id": task.task_id, "filters": filters},
        )
        await ctx.cache.set(cache_key, bundle)
        return bundle
