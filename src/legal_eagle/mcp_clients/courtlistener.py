"""CourtListener REST client (US federal & state case law).

Public docs: https://www.courtlistener.com/help/api/rest/
End-point used: /api/rest/v4/search/?q=...&type=o&court=...
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

import httpx

from ..config import get_settings
from ..schemas.legal_document import (
    DocumentBundle,
    DocumentType,
    Jurisdiction,
    LegalDocument,
)
from ._http import get_json

logger = logging.getLogger(__name__)


class CourtListenerClient:
    """Async REST client for CourtListener's v4 search API."""

    def __init__(self, base_url: Optional[str] = None, token: Optional[str] = None) -> None:
        s = get_settings()
        self.base_url = (base_url or s.courtlistener_base_url).rstrip("/")
        self.token = token or s.courtlistener_api_token
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "CourtListenerClient":
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Token {self.token}"
        self._client = httpx.AsyncClient(headers=headers)
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("CourtListenerClient must be used as async context manager")
        return self._client

    async def search_opinions(
        self,
        query: str,
        *,
        court: Optional[str] = None,
        date_after: Optional[str] = None,
        date_before: Optional[str] = None,
        max_results: int = 10,
    ) -> DocumentBundle:
        """Search US case law opinions. Returns a normalized DocumentBundle."""
        params: dict[str, Any] = {
            "q": query,
            "type": "o",  # opinions
            "format": "json",
        }
        if court:
            params["court"] = court
        if date_after:
            params["filed_after"] = date_after
        if date_before:
            params["filed_before"] = date_before

        url = f"{self.base_url}/search/"
        data = await get_json(self.client, url, params=params)
        results: list[dict[str, Any]] = data.get("results", [])[:max_results]

        docs: list[LegalDocument] = []
        for r in results:
            try:
                docs.append(self._normalize(r))
            except Exception as e:  # noqa: BLE001
                logger.warning("Skipping CourtListener record: %s", e)
        return DocumentBundle(
            jurisdiction=Jurisdiction.US,
            documents=docs,
            query_used=query,
        )

    async def get_opinion_by_id(self, opinion_id: str | int) -> LegalDocument:
        url = f"{self.base_url}/opinions/{opinion_id}/"
        data = await get_json(self.client, url)
        return self._normalize(data)

    def _normalize(self, raw: dict[str, Any]) -> LegalDocument:
        # CourtListener search results nest the opinion under "opinions" or return it directly
        opinion = raw.get("opinions") or raw
        if isinstance(opinion, list) and opinion:
            opinion = opinion[0]
        opinion_id = (
            opinion.get("id")
            or opinion.get("cluster_id")
            or raw.get("id")
            or uuid.uuid4().hex
        )
        case_name = (
            opinion.get("case_name")
            or raw.get("caseName")
            or raw.get("case_name")
            or "(Untitled)"
        )
        date_decided = (
            opinion.get("date_filed")
            or raw.get("dateFiled")
            or raw.get("date_filed")
        )
        court = (
            opinion.get("court")
            or raw.get("court")
            or raw.get("court_id")
        )
        if isinstance(court, dict):
            court = court.get("name") or court.get("id")
        citations = []
        for c in raw.get("citation", []) or []:
            if isinstance(c, dict):
                citations.append(str(c.get("cite") or c))
            else:
                citations.append(str(c))
        text = (
            opinion.get("plain_text")
            or opinion.get("html")
            or opinion.get("html_with_citations")
            or raw.get("snippet")
            or ""
        )
        if isinstance(text, str):
            text = text[:8000]  # respect context window
        url = (
            opinion.get("absolute_url")
            or raw.get("absolute_url")
            or raw.get("url")
            or f"https://www.courtlistener.com/opinion/{opinion_id}/"
        )
        if url and url.startswith("/"):
            url = f"https://www.courtlistener.com{url}"
        return LegalDocument(
            document_id=f"us:{opinion_id}",
            jurisdiction=Jurisdiction.US,
            title=str(case_name),
            document_type=DocumentType.OPINION,
            full_text=text,
            metadata={
                "court": court,
                "docket_number": opinion.get("docket_number") or raw.get("docketNumber"),
                "status": raw.get("status"),
            },
            citations=citations,
            cited_by=[],
            url=url,
            relevance_score=float(raw.get("score", 0.0) or 0.0),
            date_decided=str(date_decided) if date_decided else None,
            court_or_body=str(court) if court else None,
            provenance_id=uuid.uuid4().hex,
        )
