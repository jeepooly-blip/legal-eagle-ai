"""JSON handoff schemas for inter-agent communication.

Per PRD section 5, agents exchange five types of structured payloads:
- Research Task        (Orchestrator -> Retriever)
- Result Return        (Retriever -> Summarizer / Orchestrator)
- Synthesis            (Summarizer -> Synthesis Agent)
- Verification         (Verification Agent -> final report)
- Control              (Orchestrator control signals, e.g. retry/cancel)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from .legal_document import DocumentBundle, Jurisdiction


class ResearchTask(BaseModel):
    """Orchestrator -> Retriever."""

    task_id: str
    parent_session_id: str
    jurisdiction: Jurisdiction
    query: str
    filters: dict[str, Any] = Field(default_factory=dict)
    max_results: int = Field(default=10, ge=1, le=50)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ResultReturn(BaseModel):
    """Retriever -> Orchestrator / Summarizer."""

    task_id: str
    parent_session_id: str
    jurisdiction: Jurisdiction
    status: str = Field(description="'ok' | 'partial' | 'failed'")
    error: Optional[str] = None
    bundle: Optional[DocumentBundle] = None
    completed_at: datetime = Field(default_factory=datetime.utcnow)


class SummaryItem(BaseModel):
    document_id: str
    title: str
    holdings: list[str] = Field(default_factory=list)
    key_facts: list[str] = Field(default_factory=list)
    legal_basis: list[str] = Field(default_factory=list)
    procedural: dict[str, Any] = Field(
        default_factory=dict,
        description="stage, posture, timelines, burdens, remedies",
    )


class SummarizedBundle(BaseModel):
    jurisdiction: Jurisdiction
    items: list[SummaryItem]
    summary_text: str = Field(default="", description="LLM-generated overall summary")
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    eurovoc_descriptors: list[str] = Field(
        default_factory=list,
        description="Top EuroVoc concepts aggregated across the bundle (EU only).",
    )


class SynthesisPayload(BaseModel):
    """Summarizer -> Synthesis Agent and Synthesis -> Verification."""

    session_id: str
    us_summary: Optional[SummarizedBundle] = None
    eu_summary: Optional[SummarizedBundle] = None
    alignment_matrix: list[dict[str, Any]] = Field(default_factory=list)
    divergences: list[dict[str, Any]] = Field(default_factory=list)
    similar_precedents: list[dict[str, Any]] = Field(default_factory=list)
    narrative: str = Field(default="", description="Cross-jurisdictional comparative narrative")
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    eurovoc_bridge: list[dict[str, Any]] = Field(
        default_factory=list,
        description="EuroVoc ↔ US concept mappings the Synthesis Agent applied.",
    )
    eurovoc_hierarchy: list[dict[str, Any]] = Field(
        default_factory=list,
        description="EuroVoc hierarchies consulted (concept, parents, children).",
    )


class VerificationFlag(BaseModel):
    document_id: Optional[str] = None
    severity: str = Field(description="'info' | 'warning' | 'error'")
    code: str
    message: str


class VerificationReport(BaseModel):
    session_id: str
    passed: bool
    citation_validation_rate: float = Field(ge=0.0, le=1.0)
    flags: list[VerificationFlag] = Field(default_factory=list)
    verified_at: datetime = Field(default_factory=datetime.utcnow)


class ControlSignal(BaseModel):
    """Orchestrator control: retry, cancel, request-more."""

    task_id: str
    parent_session_id: str
    action: str = Field(description="'retry' | 'cancel' | 'request_more' | 'finalize'")
    payload: dict[str, Any] = Field(default_factory=dict)
    issued_at: datetime = Field(default_factory=datetime.utcnow)


class EuroVocConcept(BaseModel):
    """A single EuroVoc thesaurus concept returned by EuroVoc MCP tools."""

    uri: str = Field(description="EuroVoc concept URI, e.g. 'http://eurovoc.europa.eu/123'")
    pref_label: str = Field(description="Preferred English label")
    alt_labels: list[str] = Field(default_factory=list)
    domain: Optional[str] = Field(default=None, description="Top-level EuroVoc domain, e.g. 'Politics'")
    microthesaurus: Optional[str] = Field(default=None, description="Microthesaurus code, e.g. '04'")
    broader: list[str] = Field(default_factory=list, description="Broader concept URIs")
    narrower: list[str] = Field(default_factory=list, description="Narrower concept URIs")
    related: list[str] = Field(default_factory=list, description="Related concept URIs")
    language: str = Field(default="en")


class EuroVocBridgeEntry(BaseModel):
    """A single US ↔ EuroVoc concept mapping produced by `eurlex_eurovoc_bridge`."""

    eurovoc_uri: str
    eurovoc_label: str
    us_concept: str
    rationale: str = Field(default="", description="Why these are considered equivalent/analogous")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


__all__ = [
    "ResearchTask",
    "ResultReturn",
    "SummaryItem",
    "SummarizedBundle",
    "SynthesisPayload",
    "VerificationFlag",
    "VerificationReport",
    "ControlSignal",
    "EuroVocConcept",
    "EuroVocBridgeEntry",
]
