"""Epistemic confidence — an honest, auditable trust score for a decision.

A decision is never more reliable than its weakest supporting link. This computes
a Confidence Score from the evidence actually behind a decision, via the FPF
aggregation invariants (Gödel t-norm ⇒ **WLNK = min**, with IDEM dedup; COMM/LOC
hold by construction):

  • formality caps reliability   — F0 (raw) can't exceed 0.70, F3 (verifiable) 1.0;
  • empirical evidence decays    — past its `valid_until` window its weight drops;
  • unsupported claims are capped — a bare hypothesis can't score above 0.5;
  • the score is the weak link    — one shaky claim caps the whole decision.

The result carries *why* — the weakest link and staleness — so the number is an
audit trail, not a vibe. Pure stdlib.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .ontology import DecisionRecord, Evidence
from .validator import KnowledgeBase

_CEILING = {"F0": 0.70, "F1": 0.85, "F2": 0.95, "F3": 1.0}
_UNSUPPORTED_CAP = 0.5  # a claim with no evidence is a bare hypothesis
_DECAY = 0.2  # reliability drop once evidence is past its validity window
_CONGRUENCE_PENALTY = 0.9  # applied when support crosses bounded contexts


def formality_ceiling(formality: str) -> float:
    return _CEILING.get(formality, 0.70)


def _parse_date(s: Optional[str]) -> Optional[datetime]:
    """Lenient parse of a date/period string (ISO, YYYY-MM-DD, YYYY-MM, YYYY, YYYY-Qn)."""
    if not s:
        return None
    s = s.strip()
    for length, fmt in ((10, "%Y-%m-%d"), (7, "%Y-%m"), (4, "%Y")):
        try:
            return datetime.strptime(s[:length], fmt)
        except ValueError:
            continue
    return None


def effective_reliability(ev: Evidence, now: datetime) -> float:
    """Evidence reliability after the formality ceiling and temporal decay."""
    r = min(ev.reliability, formality_ceiling(ev.formality))
    end = _parse_date(ev.valid_until)
    if end is not None and now > end:
        r = max(0.0, r - _DECAY)
    return r


def gamma(values: list[float]) -> float:
    """WLNK aggregation: the weak link. IDEM: duplicate values don't add weight."""
    uniq = list(dict.fromkeys(round(v, 6) for v in values))
    return min(uniq) if uniq else 0.0


def claim_reliability(claim_id: str, kb: KnowledgeBase, now: datetime) -> tuple[float, str]:
    """A claim is as strong as its weakest evidence; unsupported ⇒ bare hypothesis."""
    evs = [e for e in kb.evidence.values() if e.target_claim_id == claim_id]
    if not evs:
        return _UNSUPPORTED_CAP, "F0"
    r = gamma([effective_reliability(e, now) for e in evs])
    weakest_formality = min((e.formality for e in evs), key=formality_ceiling)
    return r, weakest_formality


@dataclass
class DecisionConfidence:
    score: float
    band: str  # "high" | "medium" | "low"
    weakest_link: Optional[str]  # id (or note) of what caps the score
    stale: bool
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "score": round(self.score, 3),
            "band": self.band,
            "weakest_link": self.weakest_link,
            "stale": self.stale,
            "notes": self.notes,
        }


def _band(score: float) -> str:
    return "high" if score >= 0.75 else "medium" if score >= 0.5 else "low"


def decision_confidence(
    decision: DecisionRecord, kb: KnowledgeBase, now: Optional[datetime] = None
) -> DecisionConfidence:
    """Honest confidence for a decision: the weak link across its supporting claims."""
    now = now or datetime.utcnow()
    notes: list[str] = []
    supporting = decision.supporting_claim_ids

    if not supporting:
        notes.append("decision has no supporting claims")
        return DecisionConfidence(0.4, _band(0.4), "(no supporting claims)", False, notes)

    per_claim: list[tuple[str, float]] = []
    contexts: set[str] = set()
    stale = False
    for cid in supporting:
        r, _f = claim_reliability(cid, kb, now)
        per_claim.append((cid, r))
        claim = kb.claims.get(cid)
        if claim is not None:
            contexts.add(claim.context_id)
        for e in kb.evidence.values():
            if e.target_claim_id == cid:
                end = _parse_date(e.valid_until)
                if end is not None and now > end:
                    stale = True

    score = gamma([r for _c, r in per_claim])
    weakest = min(per_claim, key=lambda cr: cr[1])[0]

    if len(contexts) > 1:  # congruence penalty: support crosses frames
        score *= _CONGRUENCE_PENALTY
        notes.append(f"congruence penalty: support crosses {len(contexts)} contexts")

    if decision.verify_after is not None:
        va = _parse_date(decision.verify_after)
        if va is not None and now > va:
            stale = True
            notes.append("past verify_after — decision is due for re-verification")
    if stale:
        notes.append("stale evidence — re-verify before relying on this")

    return DecisionConfidence(score, _band(score), weakest, stale, notes)
