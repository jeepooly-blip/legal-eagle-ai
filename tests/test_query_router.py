"""Unit tests for the query router."""

from legal_eagle.middleware.query_router import detect_jurisdictions, route
from legal_eagle.schemas.legal_document import Jurisdiction


def test_detects_us_only() -> None:
    qs = [
        "What does the U.S. Supreme Court say about the Fourth Amendment?",
        "Warrantless search under American law",
        "First Amendment commercial speech",
    ]
    for q in qs:
        out = detect_jurisdictions(q)
        assert Jurisdiction.US in out, q


def test_detects_eu_only() -> None:
    qs = [
        "How does the GDPR regulate employee monitoring in the European Union?",
        "CJEU ruling on cross-border data transfers",
        "European Commission directive on platform workers",
    ]
    for q in qs:
        out = detect_jurisdictions(q)
        assert Jurisdiction.EU in out, q


def test_defaults_to_both_when_ambiguous() -> None:
    out = detect_jurisdictions("Compare privacy rights across jurisdictions")
    assert Jurisdiction.US in out
    assert Jurisdiction.EU in out


def test_route_respects_override() -> None:
    out = route("anything", override=[Jurisdiction.EU])
    assert out == [Jurisdiction.EU]
