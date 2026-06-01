"""End-to-end pipeline test with stubbed MCP clients + LLM.

Verifies the full flow: orchestrator -> retrievers -> summarizer -> synthesis -> verification.
"""

from typing import Any

import pytest

from legal_eagle.llm.client import LLMClient
from legal_eagle.pipeline import ResearchPipeline
from legal_eagle.schemas.legal_document import (
    DocumentBundle,
    DocumentType,
    Jurisdiction,
    LegalDocument,
)
from legal_eagle.schemas.task_handoff import ResearchTask


class _StubLLM(LLMClient):
    def __init__(self) -> None:
        super().__init__()
        self._scripts: list[dict[str, Any]] = [
            # Orchestrator decomposition
            {
                "us": {"query": "first amendment commercial speech", "filters": {}, "max_results": 3},
                "eu": {"query": "GDPR data protection employee monitoring", "filters": {}, "max_results": 3},
                "jurisdictions": ["us", "eu"],
            },
            # US summarizer
            {
                "items": [
                    {
                        "document_id": "us:1",
                        "title": "Central Hudson",
                        "holdings": ["Commercial speech is protected but subject to regulation."],
                        "key_facts": ["Utility advertising."],
                        "legal_basis": ["First Amendment"],
                        "procedural": {},
                    }
                ],
                "summary_text": "US protects commercial speech subject to regulation.",
            },
            # EU summarizer
            {
                "items": [
                    {
                        "document_id": "eu:1",
                        "title": "GDPR",
                        "holdings": ["Personal data must be processed lawfully."],
                        "key_facts": ["Cross-border employee monitoring."],
                        "legal_basis": ["Regulation 2016/679"],
                        "procedural": {},
                    }
                ],
                "summary_text": "EU requires lawful basis for processing personal data.",
            },
            # Synthesis
            {
                "alignment_matrix": [
                    {
                        "principle": "freedom of expression vs privacy",
                        "us_position": "First Amendment favors speech",
                        "eu_position": "GDPR favors data subject rights",
                        "status": "divergent",
                    }
                ],
                "divergences": [
                    {
                        "topic": "employee monitoring",
                        "us_view": "Limited restrictions.",
                        "eu_view": "Strict lawful-basis requirements.",
                        "implication": "Different compliance regimes.",
                    }
                ],
                "similar_precedents": [
                    {"us_doc_id": "us:1", "eu_doc_id": "eu:1", "shared_principle": "regulating commercial/data flows"}
                ],
                "narrative": "US leans speech-protective; EU leans privacy-protective.",
            },
            # Verification
            {
                "passed": True,
                "citation_validation_rate": 0.95,
                "flags": [],
            },
        ]
        self._i = 0

    def complete_json(
        self,
        system: str,
        user: str,
        schema_hint=None,  # type: ignore[override]
        temperature: float = 0.0,
        max_tokens: int = 2000,
    ) -> dict[str, Any]:
        v = self._scripts[self._i % len(self._scripts)]
        self._i += 1
        return v


class _StubUSRetriever:
    async def run(self, task: ResearchTask, ctx):  # type: ignore[no-untyped-def]
        doc = LegalDocument(
            document_id="us:1",
            jurisdiction=Jurisdiction.US,
            title="Central Hudson Gas v. PSC",
            document_type=DocumentType.OPINION,
            full_text="Commercial speech doctrine...",
            url="https://example.com/us/1",
            citations=["447 U.S. 557"],
            provenance_id="prov-us-1",
        )
        return DocumentBundle(
            jurisdiction=Jurisdiction.US,
            documents=[doc],
            query_used=task.query,
        )


class _StubEURetriever:
    async def run(self, task: ResearchTask, ctx):  # type: ignore[no-untyped-def]
        doc = LegalDocument(
            document_id="eu:1",
            jurisdiction=Jurisdiction.EU,
            title="GDPR",
            document_type=DocumentType.REGULATION,
            full_text="Regulation on personal data processing...",
            url="https://example.com/eu/1",
            celex="32016R0679",
            provenance_id="prov-eu-1",
            eurovoc_descriptors=["protection of private life", "personal data"],
        )
        return DocumentBundle(
            jurisdiction=Jurisdiction.EU,
            documents=[doc],
            query_used=task.query,
        )


@pytest.mark.asyncio
async def test_pipeline_end_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    # Patch the retrievers the orchestrator imports
    from legal_eagle.agents import orchestrator as orch_mod

    monkeypatch.setattr(orch_mod, "USRetriever", _StubUSRetriever)
    monkeypatch.setattr(orch_mod, "EURRetriever", _StubEURetriever)

    llm = _StubLLM()
    pipeline = ResearchPipeline(llm=llm)
    report = await pipeline.run(
        "Compare US commercial speech protection with EU GDPR data protection"
    )

    assert report.session_id
    assert report.us_summary is not None and report.us_summary.items
    assert report.eu_summary is not None and report.eu_summary.items
    assert report.synthesis is not None
    assert report.synthesis.alignment_matrix
    assert report.synthesis.narrative
    assert report.verification is not None
    assert report.verification.passed is True
    # No hallucinated doc_ids in narrative
    from legal_eagle.agents.verification import _DOC_ID_RE

    referenced = set(_DOC_ID_RE.findall(report.synthesis.narrative or ""))
    valid = {d.document_id for d in report.us_documents + report.eu_documents}
    assert referenced <= valid, f"Narrative references unknown ids: {referenced - valid}"
    # v1.1 EuroVoc enrichment surfaces in the synthesis
    assert report.synthesis.eurovoc_bridge or report.synthesis.eurovoc_hierarchy, (
        "Synthesis should carry EuroVoc bridge/hierarchy from the orchestrator's suggest"
    )
