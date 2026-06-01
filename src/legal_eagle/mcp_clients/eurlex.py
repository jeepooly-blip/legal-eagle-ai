"""EUR-Lex REST + SPARQL client (EU legislation, directives, regulations, CJEU judgments).

Approach: Use the public EUR-Lex search HTML endpoint for keyword search and
the publications.europa.eu SPARQL endpoint (Cellar) to fetch document
metadata. The combined `get_document_by_celex` returns a normalized record
for a given CELEX number.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any, Optional
from urllib.parse import quote_plus

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

# CELEX pattern: sector + year + document-type digit + sequence
CELEX_RE = re.compile(r"^\d{1}[A-Z]?\d{4}[A-Z]\d{4}$", re.IGNORECASE)


class EURLexClient:
    """Async client for EUR-Lex + EU Publications SPARQL endpoint."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        sparql_endpoint: Optional[str] = None,
    ) -> None:
        s = get_settings()
        self.base_url = (base_url or s.eurlex_base_url).rstrip("/")
        self.sparql_endpoint = sparql_endpoint or s.eurlex_sparql_endpoint
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "EURLexClient":
        self._client = httpx.AsyncClient(
            headers={
                "Accept": "application/json",
                "User-Agent": "LegalEagleAI/0.1 (+https://github.com/)",
            }
        )
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("EURLexClient must be used as async context manager")
        return self._client

    async def expert_search(
        self,
        query: str,
        *,
        document_type: Optional[str] = None,
        max_results: int = 10,
    ) -> DocumentBundle:
        """Search EUR-Lex and return normalized results.

        Strategy: try SPARQL full-text first (best signal), then fall back to
        the EUR-Lex HTML search page parsed for CELEX numbers and titles.
        """
        try:
            celexes = await self._sparql_search(query, limit=max_results)
        except Exception as e:  # noqa: BLE001
            logger.warning("SPARQL search failed (%s); falling back to HTML", e)
            celexes = await self._html_search(query, limit=max_results)

        docs: list[LegalDocument] = []
        for celex in celexes[:max_results]:
            try:
                docs.append(await self.get_document_by_celex(celex))
            except Exception as e:  # noqa: BLE001
                logger.warning("Skipping CELEX %s: %s", celex, e)
        if not docs and celexes == []:
            # Even on no results, return an empty bundle
            return DocumentBundle(
                jurisdiction=Jurisdiction.EU, documents=[], query_used=query
            )
        return DocumentBundle(
            jurisdiction=Jurisdiction.EU, documents=docs, query_used=query
        )

    async def get_document_by_celex(self, celex: str) -> LegalDocument:
        celex = celex.strip().upper()
        # Try Cellar SPARQL for title and metadata
        try:
            meta = await self._cellar_metadata(celex)
        except Exception as e:  # noqa: BLE001
            logger.debug("Cellar metadata fetch failed for %s: %s", celex, e)
            meta = {}
        # Pull EuroVoc descriptors (best-effort; tolerate failures)
        try:
            eurovoc_labels = await self._eurovoc_for_celex(celex)
        except Exception as e:  # noqa: BLE001
            logger.debug("EuroVoc fetch failed for %s: %s", celex, e)
            eurovoc_labels = []
        title = meta.get("title") or f"EU document {celex}"
        doc_type = _detect_doc_type(celex, meta.get("type"))
        url = meta.get("url") or f"{self.base_url}/legal-content/EN/TXT/?uri=CELEX:{celex}"
        text = await self._fetch_text(celex)
        return LegalDocument(
            document_id=f"eu:{celex}",
            jurisdiction=Jurisdiction.EU,
            title=title,
            document_type=doc_type,
            full_text=text,
            metadata=meta,
            citations=[],
            cited_by=[],
            url=url,
            relevance_score=0.0,
            date_decided=meta.get("date"),
            court_or_body=meta.get("author") or "European Union",
            celex=celex,
            eurovoc_descriptors=eurovoc_labels,
            provenance_id=uuid.uuid4().hex,
        )

    async def _eurovoc_for_celex(self, celex: str) -> list[str]:
        """Return English prefLabels of EuroVoc concepts tagged on a CELEX work."""
        sparql = f"""
        PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
        PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
        SELECT DISTINCT ?label WHERE {{
          <http://publications.europa.eu/resource/celex/{celex}>
              cdm:work_is_about_concept_eurovoc ?concept .
          ?concept skos:prefLabel ?label . FILTER (lang(?label) = "en")
        }} LIMIT 25
        """
        url = f"{self.sparql_endpoint}?query={quote_plus(sparql)}&format=application/json"
        try:
            data = await get_json(self.client, url)
        except Exception:  # noqa: BLE001
            return []
        return [
            b.get("label", {}).get("value", "")
            for b in data.get("results", {}).get("bindings", [])
            if b.get("label", {}).get("value")
        ]

    # --- internals -----------------------------------------------------------

    async def _sparql_search(self, query: str, limit: int = 10) -> list[str]:
        """Use the EU Publications SPARQL endpoint to find CELEX numbers by text."""
        sparql = f"""
        PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
        PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
        PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
        SELECT DISTINCT ?celex WHERE {{
          ?work cdm:resource_legal_id_celex ?celex .
          ?work cdm:work_date_document ?date .
          OPTIONAL {{ ?work cdm:work_is_about_concept_eurovoc ?eurovoc }}
          OPTIONAL {{ ?expr cdm:expression_belongs_to_work ?work ;
                          cdm:expression_uses_language <http://publications.europa.eu/resource/authority/language/ENG> ;
                          cdm:expression_title ?title }}
          FILTER (REGEX(STR(?celex), "^[0-9]")) .
          FILTER (CONTAINS(LCASE(STR(?title)), LCASE("{_sparql_escape(query)}")) ||
                  CONTAINS(LCASE(STR(?eurovoc)), LCASE("{_sparql_escape(query)}")))
        }} LIMIT {limit}
        """
        url = f"{self.sparql_endpoint}?query={quote_plus(sparql)}&format=application/json"
        data = await get_json(self.client, url)
        bindings = data.get("results", {}).get("bindings", [])
        out: list[str] = []
        for b in bindings:
            v = b.get("celex", {}).get("value", "")
            tail = v.rsplit("/", 1)[-1]
            if tail:
                out.append(tail)
        return out

    async def _cellar_metadata(self, celex: str) -> dict[str, Any]:
        sparql = f"""
        PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
        PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
        SELECT ?title ?date ?type WHERE {{
          <http://publications.europa.eu/resource/celex/{celex}>
              cdm:work_date_document ?date .
          OPTIONAL {{
            ?expr cdm:expression_belongs_to_work <http://publications.europa.eu/resource/celex/{celex}> ;
                    cdm:expression_uses_language <http://publications.europa.eu/resource/authority/language/ENG> ;
                    cdm:expression_title ?title .
          }}
          OPTIONAL {{
            <http://publications.europa.eu/resource/celex/{celex}> a ?type .
          }}
        }} LIMIT 1
        """
        url = f"{self.sparql_endpoint}?query={quote_plus(sparql)}&format=application/json"
        data = await get_json(self.client, url)
        bindings = data.get("results", {}).get("bindings", [])
        if not bindings:
            return {}
        b = bindings[0]
        return {
            "title": (b.get("title") or {}).get("value"),
            "date": (b.get("date") or {}).get("value"),
            "type": (b.get("type") or {}).get("value"),
        }

    async def _html_search(self, query: str, limit: int = 10) -> list[str]:
        """Fallback: scrape the EUR-Lex HTML search results for CELEX numbers."""
        url = (
            f"{self.base_url}/search.html?text={quote_plus(query)}"
            "&scope=EURLEX&type=quick&lang=en"
        )
        resp = await self.client.get(url, timeout=30.0)
        if resp.status_code != 200:
            return []
        text = resp.text
        # Look for "CELEX:3..." or "celex/3..." patterns
        celexes = re.findall(
            r"(?:CELEX[:%2F/]+|celex/)([0-9][A-Z0-9]{8})", text, flags=re.IGNORECASE
        )
        seen: set[str] = set()
        out: list[str] = []
        for c in celexes:
            cu = c.upper()
            if cu not in seen:
                seen.add(cu)
                out.append(cu)
            if len(out) >= limit:
                break
        return out

    async def _fetch_text(self, celex: str) -> str:
        """Try to fetch a text excerpt for the document."""
        url = (
            f"{self.base_url}/legal-content/EN/TXT/HTML/?uri=CELEX:{celex}&isAdvanced=true"
        )
        try:
            resp = await self.client.get(url, timeout=30.0)
            if resp.status_code != 200:
                return ""
            # Naive HTML strip
            body = re.sub(r"<[^>]+>", " ", resp.text)
            body = re.sub(r"\s+", " ", body).strip()
            return body[:8000]
        except Exception:  # noqa: BLE001
            return ""


def _sparql_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _detect_doc_type(celex: str, type_uri: Optional[str]) -> DocumentType:
    """Heuristic: a CELEX like 32016R0679 has sector 3, year 2016, type R (regulation)."""
    s = celex.upper()
    if len(s) >= 4 and s[3].isdigit():
        ch = s[3]
        return {
            "R": DocumentType.REGULATION,
            "L": DocumentType.DIRECTIVE,  # actually 'directive' in CELEX parlance
            "D": DocumentType.DECISION,
            "J": DocumentType.JUDGMENT,
            "T": DocumentType.TREATY,
            "E": DocumentType.REGULATION,  # 'E' in some older CELEX
        }.get(ch, DocumentType.OTHER)
    return DocumentType.OTHER
