"""Top-level pipeline: orchestrates the full research workflow end-to-end."""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from .agents.context import AgentContext
from .agents.orchestrator import Orchestrator
from .agents.summarizer import Summarizer
from .agents.synthesis import SynthesisAgent
from .agents.verification import VerificationAgent
from .db import DB
from .llm.client import LLMClient
from .middleware.cache import TTLCache
from .middleware.provenance import ProvenanceTracker
from .middleware.rate_limiter import RateLimiter
from .schemas.legal_document import Jurisdiction
from .schemas.reports import ResearchReport
from .schemas.task_handoff import ResultReturn

logger = logging.getLogger(__name__)


class ResearchPipeline:
    """End-to-end research coordinator. Composes all agents and middleware."""

    def __init__(self, llm: Optional[LLMClient] = None, db: Optional[DB] = None) -> None:
        self.llm = llm or LLMClient()
        self.db = db or DB()
        self.rate_limiter = RateLimiter()
        self.cache = TTLCache()
        self.orchestrator = Orchestrator(self.llm, self.rate_limiter)
        self.summarizer = Summarizer(self.llm)
        self.synthesis = SynthesisAgent(self.llm)
        self.verification = VerificationAgent(self.llm)

    async def run(self, query: str) -> ResearchReport:
        session_id = uuid.uuid4().hex
        ctx = AgentContext(
            session_id=session_id,
            llm=self.llm,
            provenance=ProvenanceTracker(),
            cache=self.cache,
            rate_limiter=self.rate_limiter,
        )
        logger.info("Pipeline starting session=%s query=%r", session_id, query[:120])
        decomp = await self.orchestrator.decompose(query)
        tasks = self.orchestrator.build_tasks(session_id, query, decomp)
        results: list[ResultReturn] = await self.orchestrator.dispatch(ctx, tasks)

        us_bundle = next(
            (r.bundle for r in results if r.jurisdiction == Jurisdiction.US and r.bundle),
            None,
        )
        eu_bundle = next(
            (r.bundle for r in results if r.jurisdiction == Jurisdiction.EU and r.bundle),
            None,
        )

        us_summary = await self.summarizer.run(us_bundle) if us_bundle else None
        eu_summary = await self.summarizer.run(eu_bundle) if eu_bundle else None

        synthesis = await self.synthesis.run(
            session_id=session_id,
            original_query=query,
            us_summary=us_summary,
            eu_summary=eu_summary,
        )

        report = ResearchReport(
            session_id=session_id,
            original_query=query,
            us_documents=us_bundle.documents if us_bundle else [],
            eu_documents=eu_bundle.documents if eu_bundle else [],
            us_summary=us_summary,
            eu_summary=eu_summary,
            synthesis=synthesis,
            verification=None,
            metadata={
                "us_status": _status(results, Jurisdiction.US),
                "eu_status": _status(results, Jurisdiction.EU),
                "decomposition": decomp.model_dump(),
            },
        )
        report.verification = await self.verification.run(report)

        # Persist (in-memory if Supabase not configured)
        try:
            for d in report.us_documents + report.eu_documents:
                self.db.add_provenance(
                    {
                        "id": d.provenance_id,
                        "session_id": session_id,
                        "jurisdiction": d.jurisdiction.value,
                        "source": "courtlistener" if d.jurisdiction == Jurisdiction.US else "eurlex",
                        "query": query,
                        "documents_returned": 1,
                        "extra": {"document_id": d.document_id, "url": d.url},
                    }
                )
            self.db.save_report(report)
        except Exception as e:  # noqa: BLE001
            logger.warning("DB persistence failed: %s", e)

        logger.info("Pipeline finished session=%s", session_id)
        return report


def _status(results: list[ResultReturn], j: Jurisdiction) -> str:
    for r in results:
        if r.jurisdiction == j:
            return r.status
    return "skipped"
