"""Top-level research session report — the final user-facing deliverable."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from .legal_document import LegalDocument
from .task_handoff import SummarizedBundle, SynthesisPayload, VerificationReport


class ResearchReport(BaseModel):
    session_id: str
    original_query: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    us_documents: list[LegalDocument] = Field(default_factory=list)
    eu_documents: list[LegalDocument] = Field(default_factory=list)
    us_summary: Optional[SummarizedBundle] = None
    eu_summary: Optional[SummarizedBundle] = None
    synthesis: Optional[SynthesisPayload] = None
    verification: Optional[VerificationReport] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
