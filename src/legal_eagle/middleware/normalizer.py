"""Output normalizer — collapses heterogeneous API responses into LegalDocument.

This is mostly defensive: the per-jurisdiction clients already emit
LegalDocument, but normalization here handles dedup and relevance
re-ranking across bundles.
"""

from __future__ import annotations

from typing import Iterable

from ..schemas.legal_document import DocumentBundle, LegalDocument


def dedupe(bundles: Iterable[DocumentBundle]) -> list[LegalDocument]:
    """Deduplicate documents across bundles by document_id."""
    seen: set[str] = set()
    out: list[LegalDocument] = []
    for b in bundles:
        for d in b.documents:
            if d.document_id in seen:
                continue
            seen.add(d.document_id)
            out.append(d)
    return out


def rank(docs: Iterable[LegalDocument], limit: int | None = None) -> list[LegalDocument]:
    out = sorted(docs, key=lambda d: d.relevance_score, reverse=True)
    return out[:limit] if limit else out
