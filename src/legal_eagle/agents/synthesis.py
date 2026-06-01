"""Cross-Jurisdictional Synthesis Agent with EuroVoc bridge support."""

from __future__ import annotations

import json
import logging

from ..llm.client import LLMClient
from ..llm.prompts import SYNTHESIS_SYSTEM
from ..mcp_clients import EuroVocClient
from ..schemas.task_handoff import SummarizedBundle, SynthesisPayload

logger = logging.getLogger(__name__)


class SynthesisAgent:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    async def run(
        self,
        session_id: str,
        original_query: str,
        us_summary: SummarizedBundle | None,
        eu_summary: SummarizedBundle | None,
    ) -> SynthesisPayload:
        if not us_summary and not eu_summary:
            return SynthesisPayload(
                session_id=session_id,
                narrative="No summaries available to synthesize.",
            )

        # Build the LLM prompt first (synchronous, no I/O)
        user_msg = self._build_user_prompt(original_query, us_summary, eu_summary)
        raw = self.llm.complete_json(
            system=SYNTHESIS_SYSTEM,
            user=user_msg,
            schema_hint=SynthesisPayload,
            temperature=0.1,
            max_tokens=3000,
        )
        raw.pop("us_summary", None)
        raw.pop("eu_summary", None)

        # EuroVoc enrichment (PRD 5.3): bridge + hierarchy lookups
        eurovoc_bridge: list[dict] = []
        eurovoc_hierarchy: list[dict] = []
        if eu_summary and eu_summary.eurovoc_descriptors:
            try:
                eurovoc_bridge, eurovoc_hierarchy = await self._eurovoc_enrichment(
                    original_query, eu_summary.eurovoc_descriptors[:5]
                )
            except Exception as e:  # noqa: BLE001
                logger.debug("EuroVoc enrichment failed: %s", e)

        return SynthesisPayload(
            session_id=session_id,
            us_summary=us_summary,
            eu_summary=eu_summary,
            alignment_matrix=list(raw.get("alignment_matrix") or []),
            divergences=list(raw.get("divergences") or []),
            similar_precedents=list(raw.get("similar_precedents") or []),
            narrative=str(raw.get("narrative") or ""),
            eurovoc_bridge=eurovoc_bridge,
            eurovoc_hierarchy=eurovoc_hierarchy,
        )

    async def _eurovoc_enrichment(
        self, original_query: str, eurovoc_labels: list[str]
    ) -> tuple[list[dict], list[dict]]:
        """For each top EuroVoc concept: bridge to US + inspect hierarchy."""
        bridges: list[dict] = []
        hierarchies: list[dict] = []
        async with EuroVocClient() as evc:
            for label in eurovoc_labels:
                try:
                    bridge_entries = await evc.bridge(label, us_context=original_query)
                except Exception as e:  # noqa: BLE001
                    logger.debug("bridge(%r) failed: %s", label, e)
                    bridge_entries = []
                for b in bridge_entries:
                    bridges.append(
                        {
                            "eurovoc_label": b.eurovoc_label,
                            "eurovoc_uri": b.eurovoc_uri,
                            "us_concept": b.us_concept,
                            "rationale": b.rationale,
                            "confidence": b.confidence,
                        }
                    )
                try:
                    hier = await evc.hierarchy(label, relation="broader", depth=2)
                except Exception as e:  # noqa: BLE001
                    logger.debug("hierarchy(%r) failed: %s", label, e)
                    hier = {"concept": label, "found": False}
                hierarchies.append(hier)
        return bridges, hierarchies

    def _build_user_prompt(
        self,
        query: str,
        us: SummarizedBundle | None,
        eu: SummarizedBundle | None,
    ) -> str:
        parts = [f"Original query: {query}", ""]
        if us and us.items:
            parts.append("=== US SUMMARIES ===")
            parts.append(us.summary_text)
            for it in us.items:
                parts.append(
                    f"\n-- {it.document_id}: {it.title}\n"
                    f"Holdings: {json.dumps(it.holdings)}\n"
                    f"Facts: {json.dumps(it.key_facts)}\n"
                    f"Legal basis: {json.dumps(it.legal_basis)}\n"
                    f"Procedural: {json.dumps(it.procedural)}"
                )
        if eu and eu.items:
            parts.append("\n=== EU SUMMARIES ===")
            parts.append(eu.summary_text)
            if eu.eurovoc_descriptors:
                parts.append(
                    f"\nEuroVoc descriptors on this bundle: "
                    f"{', '.join(eu.eurovoc_descriptors)}"
                )
            for it in eu.items:
                parts.append(
                    f"\n-- {it.document_id}: {it.title}\n"
                    f"Holdings: {json.dumps(it.holdings)}\n"
                    f"Facts: {json.dumps(it.key_facts)}\n"
                    f"Legal basis: {json.dumps(it.legal_basis)}\n"
                    f"Procedural: {json.dumps(it.procedural)}"
                )
        return "\n".join(parts)
