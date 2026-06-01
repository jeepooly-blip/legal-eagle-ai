"""Orchestrator Agent - query intake, decomposition, parallel dispatch."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Optional

from pydantic import BaseModel, Field

from ..llm.client import LLMClient
from ..llm.prompts import DECOMPOSITION_SYSTEM
from ..mcp_clients import EuroVocClient
from ..middleware.query_router import route
from ..middleware.rate_limiter import RateLimiter
from ..schemas.legal_document import Jurisdiction
from ..schemas.task_handoff import ResearchTask, ResultReturn
from .context import AgentContext
from .us_retriever import USRetriever
from .eu_retriever import EURRetriever

logger = logging.getLogger(__name__)


class _Decomposition(BaseModel):
    us: dict = Field(default_factory=dict)
    eu: dict = Field(default_factory=dict)
    jurisdictions: list[str] = Field(default_factory=lambda: ["us", "eu"])
    eurovoc_suggestions: list[str] = Field(
        default_factory=list,
        description="EuroVoc concept labels the orchestrator surfaced for the EU retriever.",
    )


class Orchestrator:
    def __init__(self, llm: LLMClient, rate_limiter: RateLimiter) -> None:
        self.llm = llm
        self.rate_limiter = rate_limiter

    async def decompose(self, query: str) -> _Decomposition:
        # 1) LLM-driven decomposition
        raw = self.llm.complete_json(
            system=DECOMPOSITION_SYSTEM,
            user=f"User query:\n{query}",
            schema_hint=_Decomposition,
            temperature=0.0,
        )
        try:
            decomp = _Decomposition.model_validate(raw)
        except Exception as e:
            logger.warning("Decomposition validate failed (%s); using fallback", e)
            decomp = _Decomposition()

        # 2) EuroVoc-aware augmentation: ask EuroVoc to suggest concepts
        #    and inject them into the EU retriever's filters.
        try:
            async with EuroVocClient() as evc:
                concepts = await evc.suggest(query, limit=8)
            labels = [c.pref_label for c in concepts]
            decomp.eurovoc_suggestions = labels
            if decomp.eu:
                existing = decomp.eu.setdefault("filters", {})
                existing_eurovoc = existing.get("eurovoc", [])
                for label in labels:
                    if label and label not in existing_eurovoc:
                        existing_eurovoc.append(label)
                existing["eurovoc"] = existing_eurovoc
        except Exception as e:  # noqa: BLE001
            logger.debug("EuroVoc suggest during decomposition failed: %s", e)
        return decomp

    def build_tasks(
        self, session_id: str, query: str, decomposition: _Decomposition
    ) -> list[ResearchTask]:
        targets = route(query, override=self._override_jurisdictions(decomposition))
        tasks = []
        for j in targets:
            if j == Jurisdiction.US:
                plan = decomposition.us or {"query": query}
            elif j == Jurisdiction.EU:
                plan = decomposition.eu or {"query": query}
            else:
                plan = {"query": query}
            tasks.append(
                ResearchTask(
                    task_id=uuid.uuid4().hex,
                    parent_session_id=session_id,
                    jurisdiction=j,
                    query=plan.get("query") or query,
                    filters=plan.get("filters") or {},
                    max_results=int(plan.get("max_results") or 8),
                )
            )
        return tasks

    async def dispatch(self, ctx: AgentContext, tasks: list[ResearchTask]) -> list[ResultReturn]:
        coros = [self._run_one(ctx, t) for t in tasks]
        return await asyncio.gather(*coros, return_exceptions=False)

    async def _run_one(self, ctx: AgentContext, task: ResearchTask) -> ResultReturn:
        await self.rate_limiter.acquire(key=f"retriever:{task.jurisdiction.value}")
        try:
            if task.jurisdiction == Jurisdiction.US:
                retriever = USRetriever()
                bundle = await retriever.run(task, ctx)
            else:
                retriever = EURRetriever()
                bundle = await retriever.run(task, ctx)
            return ResultReturn(
                task_id=task.task_id,
                parent_session_id=task.parent_session_id,
                jurisdiction=task.jurisdiction,
                status="ok" if bundle and bundle.documents else "partial",
                bundle=bundle,
            )
        except Exception as e:
            logger.exception("Retriever failed for %s", task.jurisdiction)
            return ResultReturn(
                task_id=task.task_id,
                parent_session_id=task.parent_session_id,
                jurisdiction=task.jurisdiction,
                status="failed",
                error=str(e),
            )

    @staticmethod
    def _override_jurisdictions(d: _Decomposition) -> Optional[list[Jurisdiction]]:
        js = d.jurisdictions or []
        out = []
        for s in js:
            v = str(s).lower()
            if v in ("us", "usa", "united states"):
                out.append(Jurisdiction.US)
            elif v in ("eu", "european union"):
                out.append(Jurisdiction.EU)
        return out or None
