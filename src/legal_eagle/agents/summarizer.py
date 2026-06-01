"""Summarizer Agent — turns raw documents into structured summaries.

One summarizer handles both US and EU bundles by accepting a jurisdiction
parameter. Emits `SummarizedBundle`.
"""

from __future__ import annotations

import logging

from ..llm.client import LLMClient
from ..llm.prompts import SUMMARIZATION_SYSTEM
from ..schemas.legal_document import DocumentBundle
from ..schemas.task_handoff import SummarizedBundle, SummaryItem

logger = logging.getLogger(__name__)


class Summarizer:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    async def run(self, bundle: DocumentBundle) -> SummarizedBundle:
        if not bundle.documents:
            return SummarizedBundle(
                jurisdiction=bundle.jurisdiction,
                items=[],
                summary_text=f"No {bundle.jurisdiction.value.upper()} documents retrieved.",
            )
        user_msg = self._build_user_prompt(bundle)
        raw = self.llm.complete_json(
            system=SUMMARIZATION_SYSTEM,
            user=user_msg,
            schema_hint=SummarizedBundle,
            temperature=0.0,
            max_tokens=2500,
        )
        items_raw = raw.get("items") or []
        items: list[SummaryItem] = []
        valid_ids = {d.document_id for d in bundle.documents}
        for it in items_raw:
            doc_id = str(it.get("document_id") or "")
            if doc_id not in valid_ids:
                continue
            items.append(
                SummaryItem(
                    document_id=doc_id,
                    title=str(it.get("title") or ""),
                    holdings=list(it.get("holdings") or []),
                    key_facts=list(it.get("key_facts") or []),
                    legal_basis=list(it.get("legal_basis") or []),
                    procedural=it.get("procedural") or {},
                )
            )
        covered = {i.document_id for i in items}
        for d in bundle.documents:
            if d.document_id not in covered:
                items.append(
                    SummaryItem(
                        document_id=d.document_id,
                        title=d.title,
                        holdings=[],
                        key_facts=[],
                        legal_basis=[],
                        procedural={},
                    )
                )

        # Aggregate EuroVoc descriptors across the bundle (EU only, PRD 5.3)
        aggregated_eurovoc: list[str] = []
        seen_labels: set[str] = set()
        for d in bundle.documents:
            for label in d.eurovoc_descriptors or []:
                if label and label not in seen_labels:
                    seen_labels.add(label)
                    aggregated_eurovoc.append(label)

        return SummarizedBundle(
            jurisdiction=bundle.jurisdiction,
            items=items,
            summary_text=str(raw.get("summary_text") or ""),
            eurovoc_descriptors=aggregated_eurovoc,
        )

    def _build_user_prompt(self, bundle: DocumentBundle) -> str:
        lines: list[str] = [
            f"Jurisdiction: {bundle.jurisdiction.value.upper()}",
            f"Query: {bundle.query_used}",
            f"Documents ({len(bundle.documents)}):",
        ]
        for d in bundle.documents:
            excerpt = (d.full_text or "")[:1500]
            eurovoc_block = (
                f"\nEuroVoc: {', '.join(d.eurovoc_descriptors)}" if d.eurovoc_descriptors else ""
            )
            lines.append(
                f"\n--- {d.document_id} | {d.title} | {d.url}{eurovoc_block}\n{excerpt}\n"
            )
        return "\n".join(lines)
