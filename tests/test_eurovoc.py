"""Tests for the EuroVoc MCP client.

Covers all 5 PRD v1.1 tools (5.2.1-5.2.5) and the static fallback.
"""

import re

import httpx
import pytest
import respx

from legal_eagle.mcp_clients import EuroVocClient
from legal_eagle.mcp_clients._terminology_bridge import (
    US_TO_EUROVOC,
    lookup_by_eurovoc,
    lookup_by_us,
)


SPQ = re.compile(r"example\.invalid/sparql.*")


def _sparql_resp(bindings: list[dict]) -> dict:
    return {"results": {"bindings": bindings}}


@pytest.mark.asyncio
@respx.mock
async def test_suggest_returns_static_fallback_when_sparql_empty() -> None:
    respx.get(SPQ).mock(return_value=httpx.Response(200, json=_sparql_resp([])))
    async with EuroVocClient() as cl:
        concepts = await cl.suggest("freedom of expression")
    assert concepts, "static fallback should produce at least one match"
    labels = [c.pref_label.lower() for c in concepts]
    assert any("freedom" in lbl for lbl in labels)


@pytest.mark.asyncio
@respx.mock
async def test_suggest_parses_sparql_bindings() -> None:
    bindings = [
        {
            "uri": {"value": "http://eurovoc.europa.eu/1234"},
            "label": {"value": "data protection"},
        }
    ]
    respx.get(SPQ).mock(return_value=httpx.Response(200, json=_sparql_resp(bindings)))
    async with EuroVocClient() as cl:
        concepts = await cl.suggest("data protection")
    assert any(c.pref_label == "data protection" for c in concepts)


@pytest.mark.asyncio
@respx.mock
async def test_concept_details_resolves_label() -> None:
    # First call: _uri_for_label
    # Second call: full concept details
    respx.get(SPQ).mock(
        side_effect=[
            httpx.Response(
                200, json=_sparql_resp([{"uri": {"value": "http://eurovoc.europa.eu/4471"}}])
            ),
            httpx.Response(
                200,
                json=_sparql_resp(
                    [
                        {
                            "prefLabel": {"value": "protection of private life"},
                            "altLabel": {"value": "privacy"},
                            "broader": {"value": "http://eurovoc.europa.eu/1000"},
                            "narrower": {"value": "http://eurovoc.europa.eu/5000"},
                        }
                    ]
                ),
            ),
        ]
    )
    async with EuroVocClient() as cl:
        concept = await cl.concept_details("protection of private life")
    assert concept is not None
    assert concept.pref_label == "protection of private life"
    assert "privacy" in concept.alt_labels
    assert concept.broader == ["http://eurovoc.europa.eu/1000"]
    assert concept.narrower == ["http://eurovoc.europa.eu/5000"]


@pytest.mark.asyncio
@respx.mock
async def test_bridge_returns_static_us_analog() -> None:
    # Need to resolve "freedom of expression" via SPARQL to a URI first
    respx.get(SPQ).mock(
        side_effect=[
            httpx.Response(
                200,
                json=_sparql_resp([{"uri": {"value": "http://eurovoc.europa.eu/757"}}]),
            ),
            httpx.Response(
                200,
                json=_sparql_resp(
                    [
                        {
                            "prefLabel": {"value": "freedom of expression"},
                            "altLabel": {"value": "free speech"},
                        }
                    ]
                ),
            ),
        ]
    )
    async with EuroVocClient() as cl:
        bridges = await cl.bridge("freedom of expression", us_context="commercial speech")
    assert bridges, "expected at least one bridge entry from the static table"
    # The static table maps "freedom of expression" to First Amendment commercial speech
    labels = {b.us_concept for b in bridges}
    assert any("commercial speech" in lbl.lower() for lbl in labels)


@pytest.mark.asyncio
@respx.mock
async def test_hierarchy_returns_broader_chain() -> None:
    # 1) _uri_for_label  2) _resolve_concept details  3) walk broader
    respx.get(SPQ).mock(
        side_effect=[
            httpx.Response(
                200,
                json=_sparql_resp([{"uri": {"value": "http://eurovoc.europa.eu/3143"}}]),
            ),
            httpx.Response(
                200,
                json=_sparql_resp(
                    [
                        {
                            "prefLabel": {"value": "personal data"},
                            "altLabel": {"value": "data protection"},
                        }
                    ]
                ),
            ),
            httpx.Response(
                200,
                json=_sparql_resp(
                    [
                        {
                            "rel": {"value": "http://eurovoc.europa.eu/1000"},
                            "label": {"value": "information technology"},
                        }
                    ]
                ),
            ),
        ]
    )
    async with EuroVocClient() as cl:
        hier = await cl.hierarchy("personal data", relation="broader", depth=1)
    assert hier["found"] is True
    assert hier["broader"] == ["information technology"]


@pytest.mark.asyncio
@respx.mock
async def test_eurovoc_search_returns_celexes() -> None:
    respx.get(SPQ).mock(
        side_effect=[
            httpx.Response(
                200,
                json=_sparql_resp([{"uri": {"value": "http://eurovoc.europa.eu/4471"}}]),
            ),
            httpx.Response(
                200,
                json=_sparql_resp(
                    [
                        {
                            "prefLabel": {"value": "protection of private life"},
                            "altLabel": {"value": "privacy"},
                        }
                    ]
                ),
            ),
            # The actual search query
            httpx.Response(
                200,
                json=_sparql_resp(
                    [
                        {"celex": {"value": "http://publications.europa.eu/resource/celex/32016R0679"}},
                        {"celex": {"value": "http://publications.europa.eu/resource/celex/32000L0031"}},
                    ]
                ),
            ),
        ]
    )
    async with EuroVocClient() as cl:
        celexes = await cl.eurovoc_search("privacy")
    assert "32016R0679" in celexes
    assert "32000L0031" in celexes


def test_terminology_bridge_has_key_mappings() -> None:
    assert any("Fourth Amendment" in us for us, *_ in US_TO_EUROVOC)
    assert any("GDPR" in us or "personal data" in ev_label for us, _, ev_label, _ in US_TO_EUROVOC)
    by_us = lookup_by_us("Miranda warnings")
    assert by_us, "expected at least one EuroVoc entry for Miranda warnings"
    by_ev = lookup_by_eurovoc("freedom of expression")
    assert by_ev, "expected at least one US entry for freedom of expression"
