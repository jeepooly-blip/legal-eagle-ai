"""Supabase persistence layer.

If `SUPABASE_URL`/`SUPABASE_SERVICE_KEY` are unset, a no-op in-memory store
is used so the system runs offline. Either way the public API is the same.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from ..config import get_settings
from ..schemas.reports import ResearchReport

logger = logging.getLogger(__name__)


class _MemoryStore:
    def __init__(self) -> None:
        self.reports: dict[str, dict[str, Any]] = {}
        self.sessions: dict[str, dict[str, Any]] = {}
        self.documents: dict[str, dict[str, Any]] = {}
        self.provenance: list[dict[str, Any]] = []

    def upsert_session(self, session_id: str, original_query: str) -> None:
        self.sessions[session_id] = {
            "session_id": session_id,
            "original_query": original_query,
        }

    def upsert_document(self, doc: dict[str, Any]) -> None:
        self.documents[doc["document_id"]] = doc

    def add_provenance(self, record: dict[str, Any]) -> None:
        self.provenance.append(record)

    def save_report(self, session_id: str, report_json: str) -> None:
        self.reports[session_id] = json.loads(report_json)

    def get_report(self, session_id: str) -> Optional[dict[str, Any]]:
        return self.reports.get(session_id)


class _SupabaseStore:
    def __init__(self, url: str, key: str) -> None:
        from supabase import create_client  # type: ignore

        self.client = create_client(url, key)

    def upsert_session(self, session_id: str, original_query: str) -> None:
        self.client.table("research_sessions").upsert(
            {"session_id": session_id, "original_query": original_query}
        ).execute()

    def upsert_document(self, doc: dict[str, Any]) -> None:
        # eurovoc_descriptors is added in v1.1; tolerated as a no-op for older schemas
        try:
            self.client.table("legal_documents").upsert(doc).execute()
        except Exception:  # noqa: BLE001
            stripped = {k: v for k, v in doc.items() if k != "eurovoc_descriptors"}
            self.client.table("legal_documents").upsert(stripped).execute()

    def add_provenance(self, record: dict[str, Any]) -> None:
        self.client.table("provenance_log").insert(record).execute()

    def save_report(self, session_id: str, report_json: str) -> None:
        self.client.table("research_reports").upsert(
            {"session_id": session_id, "payload": json.loads(report_json)}
        ).execute()

    def get_report(self, session_id: str) -> Optional[dict[str, Any]]:
        r = (
            self.client.table("research_reports")
            .select("payload")
            .eq("session_id", session_id)
            .maybe_single()
            .execute()
        )
        if r and r.data:
            return r.data.get("payload")
        return None


class DB:
    """Facade selecting Supabase if configured, else an in-memory store."""

    def __init__(self) -> None:
        s = get_settings()
        if s.supabase_url and s.supabase_service_key:
            try:
                self._impl: Any = _SupabaseStore(s.supabase_url, s.supabase_service_key)
                self.kind = "supabase"
            except Exception as e:  # noqa: BLE001
                logger.warning("Supabase init failed (%s); using memory store", e)
                self._impl = _MemoryStore()
                self.kind = "memory"
        else:
            self._impl = _MemoryStore()
            self.kind = "memory"

    def save_report(self, report: ResearchReport) -> None:
        self._impl.upsert_session(report.session_id, report.original_query)
        for d in report.us_documents + report.eu_documents:
            self._impl.upsert_document(d.model_dump(mode="json"))
        self._impl.save_report(report.session_id, report.model_dump_json())

    def get_report(self, session_id: str) -> Optional[ResearchReport]:
        data = self._impl.get_report(session_id)
        if data is None:
            return None
        return ResearchReport.model_validate(data)

    def add_provenance(self, record: dict[str, Any]) -> None:
        self._impl.add_provenance(record)
