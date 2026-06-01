"""Unified `LegalDocument` schema — the canonical shape every retrieved source is normalized into."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class Jurisdiction(str, Enum):
    US = "us"
    EU = "eu"


class DocumentType(str, Enum):
    CASE = "case"
    REGULATION = "regulation"
    DIRECTIVE = "directive"
    JUDGMENT = "judgment"
    TREATY = "treaty"
    RECOMMENDATION = "recommendation"
    DECISION = "decision"
    OPINION = "opinion"
    OTHER = "other"


class LegalDocument(BaseModel):
    document_id: str = Field(description="Internal stable id, e.g. 'us:123' or 'eu:32016R0679'")
    jurisdiction: Jurisdiction
    title: str
    document_type: DocumentType
    full_text: str = Field(default="", description="Truncated body to respect context window")
    metadata: dict[str, Any] = Field(default_factory=dict)
    citations: list[str] = Field(default_factory=list)
    cited_by: list[str] = Field(default_factory=list)
    url: str
    retrieved_at: datetime = Field(default_factory=datetime.utcnow)
    provenance_id: str = Field(description="Audit-trail id linking to retrieval event")
    relevance_score: float = Field(default=0.0, ge=0.0, le=1.0)
    date_decided: Optional[str] = Field(default=None, description="ISO date string")
    court_or_body: Optional[str] = None
    celex: Optional[str] = Field(default=None, description="EU CELEX number if applicable")
    eurovoc_descriptors: list[str] = Field(
        default_factory=list,
        description="EuroVoc concept labels/URIs this document is tagged with (EU only).",
    )
    extra: dict[str, Any] = Field(default_factory=dict)


class DocumentBundle(BaseModel):
    """A retrieved set of documents for one jurisdiction."""

    jurisdiction: Jurisdiction
    documents: list[LegalDocument]
    query_used: str
    retrieved_at: datetime = Field(default_factory=datetime.utcnow)
