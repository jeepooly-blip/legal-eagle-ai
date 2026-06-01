"""Provenance tracker — records every retrieval event for auditability."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class ProvenanceRecord:
    id: str
    session_id: str
    jurisdiction: str
    source: str
    query: str
    documents_returned: int
    created_at: datetime = field(default_factory=datetime.utcnow)
    extra: dict[str, Any] = field(default_factory=dict)


class ProvenanceTracker:
    def __init__(self) -> None:
        self._records: list[ProvenanceRecord] = []

    def new_id(self) -> str:
        return uuid.uuid4().hex

    def record(
        self,
        *,
        session_id: str,
        jurisdiction: str,
        source: str,
        query: str,
        documents_returned: int,
        extra: Optional[dict[str, Any]] = None,
    ) -> ProvenanceRecord:
        rec = ProvenanceRecord(
            id=self.new_id(),
            session_id=session_id,
            jurisdiction=jurisdiction,
            source=source,
            query=query,
            documents_returned=documents_returned,
            extra=extra or {},
        )
        self._records.append(rec)
        return rec

    def all(self) -> list[ProvenanceRecord]:
        return list(self._records)

    def for_session(self, session_id: str) -> list[ProvenanceRecord]:
        return [r for r in self._records if r.session_id == session_id]
