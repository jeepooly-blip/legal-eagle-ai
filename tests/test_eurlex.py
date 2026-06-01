"""Tests for the EUR-Lex client with mocked HTTP."""

import re

import httpx
import pytest
import respx

from legal_eagle.mcp_clients import EURLexClient


@pytest.mark.asyncio
@respx.mock
async def test_expert_search_falls_back_to_html() -> None:
    # The first SPARQL call (search) returns 500 -> triggers HTML fallback
    respx.get(re.compile(r"example\.invalid/sparql")).mock(
        return_value=httpx.Response(500, text="boom")
    )
    html = """
    <html><body>
      <a href="/legal-content/EN/TXT/?uri=CELEX:32016R0679">GDPR</a>
      <a href="/legal-content/EN/TXT/?uri=CELEX:32000L0031">ePrivacy</a>
    </body></html>
    """
    respx.get(re.compile(r"example\.invalid/search\.html")).mock(
        return_value=httpx.Response(200, text=html)
    )
    # Subsequent metadata/text fetches for the CELEXes we discovered
    respx.get(re.compile(r"example\.invalid/.*celex.*")).mock(
        return_value=httpx.Response(200, json={"results": {"bindings": []}})
    )
    respx.get(re.compile(r"example\.invalid/legal-content.*")).mock(
        return_value=httpx.Response(404, text="not found")
    )

    async with EURLexClient() as cl:
        bundle = await cl.expert_search("data protection")
    assert bundle.jurisdiction.value == "eu"
    # HTML fallback should have produced empty docs (no metadata), but no exception
    assert isinstance(bundle.documents, list)
