"""Query Router — determines which jurisdiction(s) a query should target."""

from __future__ import annotations

from typing import Iterable

from ..schemas.legal_document import Jurisdiction

# Strong jurisdictional cues. A single strong cue locks routing; weaker cues
# accumulate. The orchestrator can override.
US_STRONG = {
    "u.s.", "u.s.a.", "united states", "american", "federal", "supreme court",
    "circuit", "district court", "scotus", "constitution", "first amendment",
    "fourth amendment", "fifth amendment", "fourteenth amendment", "warrant",
    "miranda", "habeas", "statute of limitations",
}
EU_STRONG = {
    "european union", "e.u.", "eu ", "gdpr", "european commission",
    "european court", "cjeu", "directive", "regulation (eu)", "eu regulation",
    "european parliament", "council of the european union", "eurovoc",
    "european data protection", "charter of fundamental rights",
}

US_WEAK = {"us court", "appeal", "circuit", "docket"}
EU_WEAK = {"union", "european", "europe"}


def detect_jurisdictions(query: str) -> list[Jurisdiction]:
    q = (query or "").lower()
    us_hits = sum(1 for kw in US_STRONG if kw in q)
    eu_hits = sum(1 for kw in EU_STRONG if kw in q)
    us_weak = sum(1 for kw in US_WEAK if kw in q)
    eu_weak = sum(1 for kw in EU_WEAK if kw in q)

    out: list[Jurisdiction] = []
    if us_hits and us_hits >= eu_hits:
        out.append(Jurisdiction.US)
    if eu_hits and eu_hits >= us_hits:
        out.append(Jurisdiction.EU)
    # Always include both if neither strong cue
    if not out:
        out = [Jurisdiction.US, Jurisdiction.EU]
    # Promote weak signals if one side has none
    if us_hits == 0 and us_weak and Jurisdiction.US not in out:
        out.append(Jurisdiction.US)
    if eu_hits == 0 and eu_weak and Jurisdiction.EU not in out:
        out.append(Jurisdiction.EU)
    return out


def route(query: str, override: Iterable[Jurisdiction] | None = None) -> list[Jurisdiction]:
    if override:
        return list(override)
    return detect_jurisdictions(query)
