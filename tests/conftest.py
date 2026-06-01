"""Conftest: ensure tests run against a stub LLM so they don't need a real key."""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Make src importable without install
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Always override sensitive env defaults for tests
os.environ.setdefault("MINIMAX_API_KEY", "test-key-not-used")
os.environ.setdefault("COURTLISTENER_BASE_URL", "https://example.invalid/api")
os.environ.setdefault("EURLEX_BASE_URL", "https://example.invalid")
os.environ.setdefault("EURLEX_SPARQL_ENDPOINT", "https://example.invalid/sparql")


import pytest  # noqa: E402

from legal_eagle.schemas.task_handoff import EuroVocConcept  # noqa: E402


class _StubEuroVocClient:
    """A no-network EuroVoc client used in tests that don't exercise it directly."""

    def __init__(self, *args, **kwargs) -> None:  # noqa: D401
        pass

    async def __aenter__(self) -> "_StubEuroVocClient":
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    async def suggest(self, query: str, limit: int = 10) -> list[EuroVocConcept]:
        return [
            EuroVocConcept(uri="http://eurovoc.europa.eu/test", pref_label=label)
            for label in ["protection of private life", "personal data"][:limit]
        ]

    async def bridge(self, eurovoc_concept: str, us_context: str | None = None):
        from legal_eagle.schemas.task_handoff import EuroVocBridgeEntry
        return [
            EuroVocBridgeEntry(
                eurovoc_uri="http://eurovoc.europa.eu/test",
                eurovoc_label=eurovoc_concept,
                us_concept="US analog",
                rationale="stub",
                confidence=0.5,
            )
        ]

    async def hierarchy(self, concept: str, relation: str = "all", depth: int = 2):
        return {"concept": concept, "uri": "", "found": True, "broader": [], "narrower": [], "related": []}

    async def eurovoc_search(self, *args, **kwargs):
        return []

    async def concept_details(self, concept: str, language: str = "en"):
        return EuroVocConcept(uri="http://eurovoc.europa.eu/test", pref_label=concept)


@pytest.fixture(autouse=True)
def _stub_eurovoc(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the real EuroVocClient with a no-network stub for all tests."""
    monkeypatch.setattr(
        "legal_eagle.agents.orchestrator.EuroVocClient", _StubEuroVocClient
    )
    monkeypatch.setattr(
        "legal_eagle.agents.eu_retriever.EuroVocClient", _StubEuroVocClient
    )
    monkeypatch.setattr(
        "legal_eagle.agents.synthesis.EuroVocClient", _StubEuroVocClient
    )
