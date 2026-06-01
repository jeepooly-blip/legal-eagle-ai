"""Verification Agent - citation validation + hallucination flags."""

from __future__ import annotations

import logging
import re

from ..llm.client import LLMClient
from ..llm.prompts import VERIFICATION_SYSTEM
from ..schemas.reports import ResearchReport
from ..schemas.task_handoff import VerificationFlag, VerificationReport

logger = logging.getLogger(__name__)


class VerificationAgent:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    async def run(self, report: ResearchReport) -> VerificationReport:
        flags = []
        valid_doc_ids = {d.document_id for d in report.us_documents + report.eu_documents}
        flags.extend(_check_supported_doc_ids(report, valid_doc_ids))
        flags.extend(_check_empty_holdings(report))
        flags.extend(_check_citation_format(report))
        try:
            llm_flags = await self._llm_audit(report)
        except Exception as e:
            logger.warning("LLM verification step failed: %s", e)
            llm_flags = []
        all_flags = flags + llm_flags
        error_count = sum(1 for f in all_flags if f.severity == "error")
        n_claims = max(1, len(report.synthesis.alignment_matrix) + len(report.synthesis.divergences))
        bad = sum(1 for f in all_flags if f.severity in ("error", "warning"))
        rate = max(0.0, 1.0 - (bad / n_claims))
        return VerificationReport(
            session_id=report.session_id,
            passed=error_count == 0,
            citation_validation_rate=rate,
            flags=all_flags,
        )

    async def _llm_audit(self, report: ResearchReport) -> list[VerificationFlag]:
        us_ids = ", ".join(d.document_id for d in report.us_documents) or "(none)"
        eu_ids = ", ".join(d.document_id for d in report.eu_documents) or "(none)"
        msg = (
            f"Original query: {report.original_query}\n\n"
            f"Valid US doc_ids: {us_ids}\nValid EU doc_ids: {eu_ids}\n\n"
            f"NARRATIVE:\n{(report.synthesis.narrative or '')[:3000]}\n\n"
            f"ALIGNMENT MATRIX:\n{_safe_dumps(report.synthesis.alignment_matrix)[:2000]}\n\n"
            f"DIVERGENCES:\n{_safe_dumps(report.synthesis.divergences)[:2000]}\n\n"
            f"Flag any claim that references a doc_id NOT in the valid list, or "
            f"any unsourced assertion. Return JSON with the schema you were given."
        )
        raw = self.llm.complete_json(
            system=VERIFICATION_SYSTEM,
            user=msg,
            temperature=0.0,
            max_tokens=1500,
        )
        out = []
        for f in raw.get("flags") or []:
            try:
                out.append(
                    VerificationFlag(
                        document_id=f.get("document_id"),
                        severity=str(f.get("severity") or "warning"),
                        code=str(f.get("code") or "UNVERIFIED"),
                        message=str(f.get("message") or ""),
                    )
                )
            except Exception:
                continue
        return out


_DOC_ID_RE = re.compile(r"\b(?:us|eu):[A-Za-z0-9-]{2,}\b")


def _check_supported_doc_ids(report: ResearchReport, valid: set[str]) -> list[VerificationFlag]:
    flags = []
    text = (
        (report.synthesis.narrative or "")
        + "\n"
        + _safe_dumps(report.synthesis.alignment_matrix)
        + "\n"
        + _safe_dumps(report.synthesis.divergences)
    )
    referenced = set(_DOC_ID_RE.findall(text))
    bad = referenced - valid
    for b in sorted(bad):
        flags.append(
            VerificationFlag(
                document_id=b,
                severity="error",
                code="UNSUPPORTED_DOC_ID",
                message=f"Synthesis references document_id {b} which was not retrieved.",
            )
        )
    return flags


def _check_empty_holdings(report: ResearchReport) -> list[VerificationFlag]:
    flags = []
    for summary in (report.us_summary, report.eu_summary):
        if not summary:
            continue
        for it in summary.items:
            if not it.holdings:
                flags.append(
                    VerificationFlag(
                        document_id=it.document_id,
                        severity="warning",
                        code="EMPTY_HOLDINGS",
                        message="Summarizer produced no holdings for this document.",
                    )
                )
    return flags


def _check_citation_format(report: ResearchReport) -> list[VerificationFlag]:
    flags = []
    for d in report.us_documents + report.eu_documents:
        if d.jurisdiction.value == "us" and not d.citations and d.document_type.value in ("opinion", "case"):
            flags.append(
                VerificationFlag(
                    document_id=d.document_id,
                    severity="info",
                    code="NO_CITATIONS",
                    message="US opinion retrieved without structured citations.",
                )
            )
    return flags


def _safe_dumps(obj) -> str:
    import json
    try:
        return json.dumps(obj, default=str)
    except Exception:
        return str(obj)
