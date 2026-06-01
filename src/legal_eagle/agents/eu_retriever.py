"""EU Retriever — wraps EUR-Lex with cache + provenance + EuroVoc."""

from __future__ import annotations

import logging

from ..mcp_clients import EURLexClient, EuroVocClient
from ..schemas.legal_document import DocumentBundle, Jurisdiction
from ..schemas.task_handoff import ResearchTask
from .context import AgentContext

logger = logging.getLogger(__name__)


class EURRetriever:
    async def run(self, task: ResearchTask, ctx: AgentContext) -> DocumentBundle:
        filters = task.filters or {}
        ev = filters.get("eurovoc")
        if isinstance(ev, list):
            eurovoc_terms = [str(x) for x in ev if x]
        elif isinstance(ev, str):
            eurovoc_terms = [ev]
        else:
            eurovoc_terms = []

        cache_key = (
            "eu",
            task.query,
            tuple(sorted((k, v) for k, v in filters.items() if k != "eurovoc")),
            tuple(eurovoc_terms),
        )
        cached = await ctx.cache.get(cache_key)
        if cached is not None:
            return cached

        async with EURLexClient() as cl:
            if eurovoc_terms:
                # Primary path: use EuroVoc-anchored search (PRD v1.1 5.2.1)
                celexes: list[str] = []
                async with EuroVocClient() as evc:
                    per_term = max(1, task.max_results // max(1, len(eurovoc_terms)))
                    for term in eurovoc_terms:
                        try:
                            celexes.extend(
                                await evc.eurovoc_search(
                                    term,
                                    include_narrower=True,
                                    include_broader=False,
                                    limit=per_term,
                                )
                            )
                        except Exception as e:  # noqa: BLE001
                            logger.debug("EuroVoc search for %r failed: %s", term, e)
                seen: set[str] = set()
                unique: list[str] = []
                for c in celexes:
                    if c and c not in seen:
                        seen.add(c)
                        unique.append(c)
                docs = []
                for celex in unique[: task.max_results]:
                    try:
                        docs.append(await cl.get_document_by_celex(celex))
                    except Exception as e:  # noqa: BLE001
                        logger.debug("CELEX fetch %s failed: %s", celex, e)
                bundle = DocumentBundle(
                    jurisdiction=Jurisdiction.EU,
                    documents=docs,
                    query_used=task.query,
                )
            else:
                # Fallback: keyword expert search
                bundle = await cl.expert_search(
                    task.query,
                    document_type=(filters.get("document_type") or [None])[0],
                    max_results=task.max_results,
                )

        ctx.provenance.record(
            session_id=task.parent_session_id,
            jurisdiction="eu",
            source="eurlex+eurovoc" if eurovoc_terms else "eurlex",
            query=task.query,
            documents_returned=len(bundle.documents),
            extra={
                "task_id": task.task_id,
                "filters": filters,
                "eurovoc_terms": eurovoc_terms,
            },
        )
        await ctx.cache.set(cache_key, bundle)
        return bundle
