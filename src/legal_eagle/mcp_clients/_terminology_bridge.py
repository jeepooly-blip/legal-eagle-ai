"""Static US <-> EuroVoc Terminology Bridge.

PRD v1.1 Appendix B requires a US legal concept -> EuroVoc descriptor mapping.
This module exposes a curated starter table that the Synthesis Agent consults.
Extend over time; entries follow the canonical EuroVoc microthesauri.

Format per entry:
    (us_concept, eurovoc_uri, eurovoc_pref_label, rationale)
"""

from __future__ import annotations

US_TO_EUROVOC: list[tuple[str, str, str, str]] = [
    # ---- Privacy / data protection ----
    (
        "Fourth Amendment search and seizure",
        "http://eurovoc.europa.eu/4471",
        "protection of private life",
        "EU Charter Art. 7 / GDPR govern personal data and private-life protection; "
        "the US Fourth Amendment is the closest constitutional analog.",
    ),
    (
        "right to privacy",
        "http://eurovoc.europa.eu/4471",
        "protection of private life",
        "US constitutional privacy doctrine maps to EU Charter Art. 7 and Art. 8 ECHR.",
    ),
    (
        "personal data processing",
        "http://eurovoc.europa.eu/3143",
        "personal data",
        "GDPR Art. 4(1) defines personal data; the US sectoral approach "
        "(HIPAA, GLBA, CCPA) covers analogous territory piecemeal.",
    ),
    (
        "data breach notification",
        "http://eurovoc.europa.eu/3143",
        "personal data",
        "US state laws (CA, NY) and GDPR Art. 33 both mandate breach notification; "
        "EuroVoc 'personal data' is the bridge concept.",
    ),
    # ---- Free speech / press ----
    (
        "First Amendment commercial speech",
        "http://eurovoc.europa.eu/757",
        "freedom of expression",
        "US commercial speech doctrine (Central Hudson) maps to EU Charter Art. 11 "
        "and the CJEU's balancing of expression against consumer protection.",
    ),
    (
        "freedom of the press",
        "http://eurovoc.europa.eu/757",
        "freedom of expression",
        "First Amendment press protection aligns with EU Charter Art. 11 freedom of expression.",
    ),
    (
        "prior restraint",
        "http://eurovoc.europa.eu/757",
        "freedom of expression",
        "US Near v. Minnesota line of cases parallels EU Charter Art. 11 jurisprudence.",
    ),
    # ---- Criminal procedure ----
    (
        "Miranda warnings",
        "http://eurovoc.europa.eu/2532",
        "rights of the defence",
        "EU Directive 2010/64/EU and Charter Art. 47 provide analogous rights to "
        "be informed of charges and to counsel.",
    ),
    (
        "right to counsel",
        "http://eurovoc.europa.eu/2532",
        "rights of the defence",
        "Gideon v. Wainwright maps to Charter Art. 47 and the Salduz line of CJEU cases.",
    ),
    (
        "warrant requirement",
        "http://eurovoc.europa.eu/2532",
        "rights of the defence",
        "US warrant clause has no single EU equivalent; the bridge concept is "
        "rights of the defence and Charter Art. 7 (private life).",
    ),
    (
        "habeas corpus",
        "http://eurovoc.europa.eu/2532",
        "rights of the defence",
        "US habeas is procedural; EU equivalents sit in Charter Art. 47 and the ECHR Art. 5.",
    ),
    # ---- Administrative / regulatory ----
    (
        "Chevron deference",
        "http://eurovoc.europa.eu/2914",
        "executive power",
        "US judicial deference to agency interpretation parallels EU principles of "
        "institutional balance and the Court's review of Commission acts.",
    ),
    (
        "rulemaking",
        "http://eurovoc.europa.eu/2914",
        "executive power",
        "US APA rulemaking has no direct EU equivalent; the bridge concept is "
        "executive power and the EU's comitology / delegated-act framework.",
    ),
    # ---- IP ----
    (
        "copyright fair use",
        "http://eurovoc.europa.eu/3932",
        "copyright",
        "US fair use (17 USC 107) maps to the EU's three-step test and the "
        "InfoSoc Directive 2001/29/EC exceptions.",
    ),
    (
        "patent infringement",
        "http://eurovoc.europa.eu/5540",
        "patent law",
        "Direct functional analog between US 35 USC 271 and EU Unitary Patent / "
        "EPC framework.",
    ),
    # ---- Labor / employment ----
    (
        "at-will employment",
        "http://eurovoc.europa.eu/2551",
        "employment contract",
        "US at-will doctrine has no direct EU counterpart; the bridge concept is "
        "the EU employment-contract framework with strong wrongful-termination protection.",
    ),
    (
        "employee monitoring",
        "http://eurovoc.europa.eu/4471",
        "protection of private life",
        "US monitoring is bounded mainly by ECPA; EU is governed by GDPR Art. 88 "
        "and the CJEU's Bărbulescu line of cases.",
    ),
    # ---- Competition ----
    (
        "antitrust Sherman Act",
        "http://eurovoc.europa.eu/1093",
        "competition law",
        "US Sherman Act and EU TFEU Arts. 101-102 are functional analogs "
        "with distinct enforcement regimes.",
    ),
    (
        "merger review",
        "http://eurovoc.europa.eu/1093",
        "competition law",
        "US Hart-Scott-Rodino and EU EUMR both govern concentrations; "
        "EuroVoc 'competition law' is the bridge.",
    ),
    # ---- Consumer ----
    (
        "unfair trade practices",
        "http://eurovoc.europa.eu/1745",
        "consumer protection",
        "US FTC Act Sec. 5 and EU Unfair Commercial Practices Directive 2005/29/EC.",
    ),
    # ---- Immigration ----
    (
        "asylum",
        "http://eurovoc.europa.eu/872",
        "asylum right",
        "US INA asylum procedure and EU Common European Asylum System share concept; "
        "procedural protections differ markedly.",
    ),
]


def lookup_by_us(us_concept: str) -> list[tuple[str, str, str]]:
    """Find EuroVoc entries whose US concept matches (case-insensitive)."""
    q = us_concept.lower()
    out: list[tuple[str, str, str]] = []
    for us, ev_uri, ev_label, rationale in US_TO_EUROVOC:
        if q in us.lower():
            out.append((ev_uri, ev_label, rationale))
    return out


def lookup_by_eurovoc(ev_label: str) -> list[tuple[str, str, str]]:
    """Find US concepts mapped to a given EuroVoc label."""
    q = ev_label.lower()
    out: list[tuple[str, str, str]] = []
    for us, ev_uri, ev_label_entry, rationale in US_TO_EUROVOC:
        if q == ev_label_entry.lower():
            out.append((us, ev_uri, rationale))
    return out
