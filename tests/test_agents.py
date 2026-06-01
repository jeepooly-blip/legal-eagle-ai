"""Unit tests for the synthesis + verification with stubbed LLM."""

from typing import Any

import pytest

from legal_eagle.agents.synthesis import SynthesisAgent
from legal_eagle.agents.verification import VerificationAgent
from legal_eagle.llm.client import LLMClient
from legal_eagle.schemas.legal_document import (
    DocumentType,
    Jurisdiction,
    LegalDocument,
)
from legal_eagle.schemas.reports import ResearchReport
from legal_eagle.schemas.task_handoff import SummarizedBundle, SummaryItem, SynthesisPayload


class _StubLLM(LLMClient):
    """LLM client that returns canned JSON for tests."""

    def __init__(self, payload: dict[str, Any]) -> None:
        super().__init__()
        self._payload = payload

    def complete_json(
        self,
        system: str,
        user: str,
        schema_hint=None,  # type: ignore[override]
        temperature: float = 0.0,
        max_tokens: int = 2000,
    ) -> dict[str, Any]:
        return self._payload


def _make_doc(jurisdiction: Jurisdiction, doc_id: str, title: str) -> LegalDocument:
    return LegalDocument(
        document_id=doc_id,
        jurisdiction=jurisdiction,
        title=title,
        document_type=DocumentType.OPINION if jurisdiction == Jurisdiction.US else DocumentType.REGULATION,
        full_text="Lorem ipsum legal text.",
        url=f"https://example.com/{doc_id}",
        provenance_id="prov-" + doc_id,
    )


@pytest.mark.asyncio
async def test_synthesis_agent_uses_stub_payload() -> None:
    payload = {
        "alignment_matrix": [
            {"principle": "privacy", "us_position": "4th Am.", "eu_position": "GDPR", "status": "aligned"}
        ],
        "divergences": [],
        "similar_precedents": [],
        "narrative": "Both regimes protect privacy, with different scopes.",
    }
    sa = SynthesisAgent(_StubLLM(payload))  # type: ignore[arg-type]
    us = SummarizedBundle(
        jurisdiction=Jurisdiction.US,
        items=[SummaryItem(document_id="us:1", title="Roe", holdings=["x"], key_facts=[], legal_basis=[])],
        summary_text="US sum",
    )
    eu = SummarizedBundle(
        jurisdiction=Jurisdiction.EU,
        items=[SummaryItem(document_id="eu:1", title="GDPR", holdings=["x"], key_facts=[], legal_basis=[])],
        summary_text="EU sum",
    )
    out = await sa.run("s1", "privacy", us, eu)
    assert out.alignment_matrix[0]["principle"] == "privacy"
    assert "Both regimes" in out.narrative
    assert out.us_summary is us
    assert out.eu_summary is eu


@pytest.mark.asyncio
async def test_verification_flags_unsupported_doc_ids() -> None:
    va = VerificationAgent(_StubLLM({"flags": []}))  # type: ignore[arg-type]
    us_doc = _make_doc(Jurisdiction.US, "us:1", "A")
    eu_doc = _make_doc(Jurisdiction.EU, "eu:1", "B")
    report = ResearchReport(
        session_id="s1",
        original_query="q",
        us_documents=[us_doc],
        eu_documents=[eu_doc],
        us_summary=SummarizedBundle(
            jurisdiction=Jurisdiction.US,
            items=[SummaryItem(document_id="us:1", title="A", holdings=["h"], key_facts=[], legal_basis=[])],
            summary_text="",
        ),
        eu_summary=SummarizedBundle(
            jurisdiction=Jurisdiction.EU,
            items=[SummaryItem(document_id="eu:1", title="B", holdings=["h"], key_facts=[], legal_basis=[])],
            summary_text="",
        ),
        synthesis=SynthesisPayload(
            session_id="s1",
            narrative="See us:999 which is fabricated.",
            alignment_matrix=[],
            divergences=[],
            similar_precedents=[],
        ),
    )
    rep = await va.run(report)
    bad = [f for f in rep.flags if f.code == "UNSUPPORTED_DOC_ID"]
    assert any(f.document_id == "us:999" for f in bad)
    assert rep.passed is False
    assert 0.0 <= rep.citation_validation_rate <= 1.0
