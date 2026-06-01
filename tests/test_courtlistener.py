"""Tests for the CourtListener client normalization with mocked HTTP."""

import re

import httpx
import pytest
import respx

from legal_eagle.mcp_clients import CourtListenerClient


@pytest.mark.asyncio
@respx.mock
async def test_search_opinions_normalizes_response() -> None:
    fake_response = {
        "count": 1,
        "results": [
            {
                "id": 12345,
                "caseName": "Roe v. Wade",
                "dateFiled": "1973-01-22",
                "court": "Supreme Court of the United States",
                "citation": ["410 U.S. 113"],
                "snippet": "Held that the right to privacy is broad enough to encompass ...",
                "absolute_url": "/opinion/12345/roe-v-wade/",
            }
        ],
    }
    respx.get(re.compile(r"https?://example\.invalid/.*")).mock(
        return_value=httpx.Response(200, json=fake_response)
    )

    async with CourtListenerClient() as cl:
        bundle = await cl.search_opinions("right to privacy")
    assert len(bundle.documents) == 1
    d = bundle.documents[0]
    assert d.document_id == "us:12345"
    assert d.jurisdiction.value == "us"
    assert "Roe" in d.title
    assert d.citations == ["410 U.S. 113"]
    assert d.url.endswith("/opinion/12345/roe-v-wade/")
