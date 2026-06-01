"""EuroVoc MCP client.

Implements the five new tools from PRD v1.1 section 5.2:
  - eurlex_eurovoc_search
  - eurlex_eurovoc_concept_details
  - eurlex_eurovoc_hierarchy
  - eurlex_eurovoc_suggest
  - eurlex_eurovoc_bridge

Backed by the Publications Office SPARQL endpoint
(https://publications.europa.eu/webapi/rdf/sparql) with an in-process
TTL cache and a static terminology bridge for US->EuroVoc mapping.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Optional
from urllib.parse import quote_plus

import httpx

from ..config import get_settings
from ..schemas.task_handoff import EuroVocBridgeEntry, EuroVocConcept
from ._http import get_json

logger = logging.getLogger(__name__)

# EuroVoc concept URIs follow this pattern
EUROVOC_URI_RE = re.compile(r"http://eurovoc\.europa\.eu/(\d+)")
EUROVOC_DOMAIN_RE = re.compile(r"domain_(\d+)", re.IGNORECASE)
EUROVOC_MT_RE = re.compile(r"mt_(\d+)", re.IGNORECASE)


class EuroVocClient:
    """Async EuroVoc client (SPARQL-backed) with TTL cache and bridge."""

    def __init__(
        self,
        sparql_endpoint: Optional[str] = None,
        cache_ttl: Optional[int] = None,
    ) -> None:
        s = get_settings()
        self.sparql_endpoint = sparql_endpoint or s.eurlex_sparql_endpoint
        self.cache_ttl = cache_ttl or s.cache_ttl_seconds
        self._client: Optional[httpx.AsyncClient] = None
        self._cache: dict[str, tuple[float, Any]] = {}
        self._cache_lock = asyncio.Lock()

    async def __aenter__(self) -> "EuroVocClient":
        self._client = httpx.AsyncClient(
            headers={"Accept": "application/json", "User-Agent": "LegalEagleAI/0.1"}
        )
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("EuroVocClient must be used as async context manager")
        return self._client

    # ---- Tool 5.2.1: eurlex_eurovoc_search --------------------------------

    async def eurovoc_search(
        self,
        eurovoc_concept: str,
        *,
        include_narrower: bool = True,
        include_broader: bool = False,
        domains: Optional[list[str]] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        document_types: Optional[list[str]] = None,
        limit: int = 20,
    ) -> list[str]:
        """Return CELEX numbers for documents tagged with the EuroVoc concept.

        Resolves the concept to its URI (if a label was passed), expands
        narrower/broader as requested, then issues a SPARQL query.
        """
        concept = await self._resolve_concept(eurovoc_concept)
        if concept is None:
            logger.info("EuroVoc concept not found: %s", eurovoc_concept)
            return []

        uris = [concept.uri]
        if include_narrower and concept.narrower:
            uris.extend(concept.narrower)
        if include_broader and concept.broader:
            uris.extend(concept.broader)

        domains_clause = ""
        if domains:
            d_filter = " || ".join(
                f'CONTAINS(LCASE(STR(?work)), LCASE("/d/{d}/"))' for d in domains
            )
            domains_clause = f"FILTER ({d_filter})"
        date_clause = ""
        if date_from:
            date_clause += f'FILTER (STR(?date) >= "{date_from}") '
        if date_to:
            date_clause += f'FILTER (STR(?date) <= "{date_to}") '
        type_clause = ""
        if document_types and "all" not in document_types:
            t_filter = " || ".join(
                f'CONTAINS(LCASE(STR(?celex)), LCASE("{t}"))' for t in document_types
            )
            type_clause = f"FILTER ({t_filter})"

        values = " ".join(f"<{u}>" for u in uris)
        sparql = f"""
        PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
        PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
        SELECT DISTINCT ?celex WHERE {{
          VALUES ?eurovoc {{ {values} }}
          ?work cdm:resource_legal_id_celex ?celex ;
                cdm:work_date_document ?date .
          ?work cdm:work_is_about_concept_eurovoc ?eurovoc .
          {domains_clause}
          {date_clause}
          {type_clause}
        }} LIMIT {limit}
        """
        data = await self._sparql(sparql)
        return [b.get("celex", {}).get("value", "").rsplit("/", 1)[-1] for b in data]

    # ---- Tool 5.2.2: eurlex_eurovoc_concept_details -----------------------

    async def concept_details(
        self, concept: str, language: str = "en"
    ) -> Optional[EuroVocConcept]:
        """Return a fully-populated EuroVocConcept or None."""
        resolved = await self._resolve_concept(concept, language=language)
        return resolved

    # ---- Tool 5.2.3: eurlex_eurovoc_hierarchy -----------------------------

    async def hierarchy(
        self,
        concept: str,
        relation: str = "all",
        depth: int = 2,
    ) -> dict[str, Any]:
        """Walk broader/narrower/related graph up to `depth` hops."""
        anchor = await self._resolve_concept(concept)
        if anchor is None:
            return {"concept": concept, "found": False, "broader": [], "narrower": [], "related": []}

        visited: set[str] = set()
        result: dict[str, list[list[str]]] = {"broader": [], "narrower": [], "related": []}

        async def walk(uri: str, d: int, direction: str) -> None:
            if d <= 0 or uri in visited:
                return
            visited.add(uri)
            rel_map = {
                "broader": ("<http://www.w3.org/2004/02/skos/core#broader>", "broader"),
                "narrower": ("<http://www.w3.org/2004/02/skos/core#narrower>", "narrower"),
                "related": ("<http://www.w3.org/2004/02/skos/core#related>", "related"),
            }
            pairs = [rel_map[direction]] if relation in ("all", direction) else []
            for pred, key in pairs:
                sparql = f"""
                PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
                SELECT ?rel ?label WHERE {{
                  <{uri}> {pred} ?rel .
                  OPTIONAL {{ ?rel skos:prefLabel ?label . FILTER (lang(?label) = "en") }}
                }} LIMIT 50
                """
                rows = await self._sparql(sparql)
                chain = []
                for r in rows:
                    rel = r.get("rel", {}).get("value", "")
                    label = r.get("label", {}).get("value", rel.rsplit("/", 1)[-1])
                    chain.append(label or rel)
                    if d > 1 and rel:
                        await walk(rel, d - 1, direction)
                result[key].append(chain)

        if relation in ("all", "broader"):
            await walk(anchor.uri, depth, "broader")
        if relation in ("all", "narrower"):
            await walk(anchor.uri, depth, "narrower")
        if relation in ("all", "related"):
            await walk(anchor.uri, depth, "related")

        return {
            "concept": concept,
            "uri": anchor.uri,
            "found": True,
            "broader": [c for c in result["broader"][0]] if result["broader"] else [],
            "narrower": [c for c in result["narrower"][0]] if result["narrower"] else [],
            "related": [c for c in result["related"][0]] if result["related"] else [],
        }

    # ---- Tool 5.2.4: eurlex_eurovoc_suggest -------------------------------

    async def suggest(self, query: str, limit: int = 10) -> list[EuroVocConcept]:
        """Suggest the most relevant EuroVoc concepts for a natural-language query.

        Strategy:
          1. Try SPARQL exact/prefix label match
          2. Fall back to keyword search across prefLabel and altLabel
        """
        q = _sparql_escape(query)
        sparql = f"""
        PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
        PREFIX eurovoc: <http://eurovoc.europa.eu/>
        SELECT DISTINCT ?uri ?label WHERE {{
          ?uri a skos:Concept ;
               skos:prefLabel ?label .
          FILTER (lang(?label) = "en" || lang(?label) = "")
          FILTER (REGEX(LCASE(STR(?label)), LCASE("{q}"), "i") ||
                  CONTAINS(LCASE(STR(?uri)), LCASE("{q}")))
        }} LIMIT {limit}
        """
        rows = await self._sparql(sparql)
        concepts: list[EuroVocConcept] = []
        for r in rows:
            uri = r.get("uri", {}).get("value", "")
            label = r.get("label", {}).get("value", "")
            if uri and label:
                concepts.append(
                    EuroVocConcept(uri=uri, pref_label=label)
                )
        # Fallback: if SPARQL returns nothing (offline / endpoint not responding),
        # serve a small static vocabulary so the orchestrator can still proceed.
        if not concepts:
            concepts = _static_suggest(query, limit)
        return concepts

    # ---- Tool 5.2.5: eurlex_eurovoc_bridge ---------------------------------

    async def bridge(
        self,
        eurovoc_concept: str,
        us_context: Optional[str] = None,
    ) -> list[EuroVocBridgeEntry]:
        """Suggest US legal concept equivalents for a EuroVoc descriptor.

        Uses the static Terminology Bridge table first, then refines via LLM
        (if available) using the us_context hint.
        """
        from ._terminology_bridge import US_TO_EUROVOC  # local import to avoid cycle

        # Reverse index: EuroVoc label -> US concept
        reverse: dict[str, list[tuple[str, str, str]]] = {}
        for us_concept, ev_uri, ev_label, rationale in US_TO_EUROVOC:
            reverse.setdefault(ev_label.lower(), []).append((us_concept, ev_uri, rationale))

        concept = await self._resolve_concept(eurovoc_concept)
        if concept is None:
            return []
        key = concept.pref_label.lower()
        candidates = reverse.get(key, [])
        # If no exact label match, try fuzzy by alt labels
        for alt in concept.alt_labels:
            candidates.extend(reverse.get(alt.lower(), []))

        out: list[EuroVocBridgeEntry] = []
        for us_concept, ev_uri, rationale in candidates[:5]:
            confidence = 0.9 if us_context and us_context.lower() in us_concept.lower() else 0.7
            out.append(
                EuroVocBridgeEntry(
                    eurovoc_uri=ev_uri,
                    eurovoc_label=concept.pref_label,
                    us_concept=us_concept,
                    rationale=rationale,
                    confidence=confidence,
                )
            )

        # If we have a us_context but no candidates, ask the LLM for an analogy
        if not out and us_context:
            llm_guess = await self._llm_bridge_guess(concept.pref_label, us_context)
            out.extend(llm_guess)
        return out

    # ---- Internals --------------------------------------------------------

    async def _resolve_concept(
        self, concept: str, language: str = "en"
    ) -> Optional[EuroVocConcept]:
        """Resolve a label or URI to a fully-populated EuroVocConcept."""
        cache_key = ("resolve", concept, language)
        cached = await self._cache_get(cache_key)
        if cached is not None:
            return cached
        if EUROVOC_URI_RE.match(concept):
            uri = concept
        else:
            uri = await self._uri_for_label(concept, language=language)
            if not uri:
                return None
        sparql = f"""
        PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
        PREFIX eurovoc: <http://eurovoc.europa.eu/>
        SELECT ?prefLabel ?altLabel ?broader ?narrower ?related ?domain ?mt WHERE {{
          <{uri}> skos:prefLabel ?prefLabel . FILTER (lang(?prefLabel) = "{language}")
          OPTIONAL {{ <{uri}> skos:altLabel ?altLabel . FILTER (lang(?altLabel) = "{language}") }}
          OPTIONAL {{ <{uri}> skos:broader ?broader }}
          OPTIONAL {{ <{uri}> skos:narrower ?narrower }}
          OPTIONAL {{ <{uri}> skos:related ?related }}
          OPTIONAL {{ <{uri}> eurovoc:domain ?domain }}
          OPTIONAL {{ <{uri}> eurovoc:microThesaurus ?mt }}
        }} LIMIT 50
        """
        rows = await self._sparql(sparql)
        if not rows:
            return None
        first = rows[0]
        pref = (first.get("prefLabel") or {}).get("value", "")
        alts: list[str] = []
        broaders: list[str] = []
        narrowers: list[str] = []
        related: list[str] = []
        domains: list[str] = []
        mts: list[str] = []
        for r in rows:
            if r.get("altLabel"):
                alts.append(r["altLabel"]["value"])
            for k, sink in (("broader", broaders), ("narrower", narrowers), ("related", related)):
                v = (r.get(k) or {}).get("value")
                if v and v not in sink:
                    sink.append(v)
            d = (r.get("domain") or {}).get("value", "")
            if d and d not in domains:
                domains.append(d)
            m = (r.get("mt") or {}).get("value", "")
            if m and m not in mts:
                mts.append(m)
        out = EuroVocConcept(
            uri=uri,
            pref_label=pref or concept,
            alt_labels=alts,
            domain=domains[0] if domains else None,
            microthesaurus=mts[0] if mts else None,
            broader=broaders,
            narrower=narrowers,
            related=related,
            language=language,
        )
        await self._cache_set(cache_key, out)
        return out

    async def _uri_for_label(self, label: str, language: str = "en") -> Optional[str]:
        cache_key = ("uri_for_label", label.lower(), language)
        cached = await self._cache_get(cache_key)
        if cached is not None:
            return cached
        sparql = f"""
        PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
        SELECT ?uri WHERE {{
          ?uri skos:prefLabel ?label . FILTER (lang(?label) = "{language}")
          FILTER (LCASE(STR(?label)) = LCASE("{_sparql_escape(label)}"))
        }} LIMIT 1
        """
        rows = await self._sparql(sparql)
        if not rows:
            return None
        uri = rows[0].get("uri", {}).get("value", "")
        await self._cache_set(cache_key, uri)
        return uri

    async def _sparql(self, query: str) -> list[dict[str, Any]]:
        url = f"{self.sparql_endpoint}?query={quote_plus(query)}&format=application/json"
        try:
            data = await get_json(self.client, url)
        except Exception as e:  # noqa: BLE001
            logger.debug("SPARQL query failed: %s", e)
            return []
        return data.get("results", {}).get("bindings", [])

    async def _cache_get(self, key: Any) -> Any:
        import time

        async with self._cache_lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            expires, value = entry
            if expires < time.time():
                self._cache.pop(key, None)
                return None
            return value

    async def _cache_set(self, key: Any, value: Any) -> None:
        import time

        async with self._cache_lock:
            self._cache[key] = (time.time() + self.cache_ttl, value)

    async def _llm_bridge_guess(
        self, eurovoc_label: str, us_context: str
    ) -> list[EuroVocBridgeEntry]:
        """Use the LLM client to suggest a US analogy when the static table misses."""
        try:
            from ..llm.client import LLMClient
            from ..llm.prompts import EUROVOC_BRIDGE_SYSTEM
        except Exception:  # pragma: no cover
            return []
        try:
            client = LLMClient()
            raw = client.complete_json(
                system=EUROVOC_BRIDGE_SYSTEM,
                user=(
                    f"EuroVoc concept: {eurovoc_label}\n"
                    f"US legal context: {us_context}\n\n"
                    f"Return JSON: {{\"bridges\": [{{\"us_concept\": \"...\", "
                    f"\"rationale\": \"...\", \"confidence\": 0.0}}]}}"
                ),
            )
        except Exception as e:  # noqa: BLE001
            logger.debug("LLM bridge guess failed: %s", e)
            return []
        out: list[EuroVocBridgeEntry] = []
        for b in raw.get("bridges") or []:
            try:
                out.append(
                    EuroVocBridgeEntry(
                        eurovoc_uri="",
                        eurovoc_label=eurovoc_label,
                        us_concept=str(b.get("us_concept") or "").strip(),
                        rationale=str(b.get("rationale") or "").strip(),
                        confidence=float(b.get("confidence") or 0.0),
                    )
                )
            except Exception:  # noqa: BLE001
                continue
        return out


# ----- Helpers ----------------------------------------------------------------


def _sparql_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def _static_suggest(query: str, limit: int) -> list[EuroVocConcept]:
    """Offline-friendly suggest fallback backed by the static bridge table."""
    from ._terminology_bridge import US_TO_EUROVOC

    q = query.lower()
    seen: set[str] = set()
    out: list[EuroVocConcept] = []
    for us_concept, ev_uri, ev_label, _rationale in US_TO_EUROVOC:
        if q in us_concept.lower() or q in ev_label.lower():
            if ev_label in seen:
                continue
            seen.add(ev_label)
            out.append(EuroVocConcept(uri=ev_uri, pref_label=ev_label))
            if len(out) >= limit:
                break
    return out
