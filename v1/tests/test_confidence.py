"""Contract for the epistemic confidence layer (F-G-R, WLNK, decay)."""

from __future__ import annotations

import unittest
from datetime import datetime

from v1.core.confidence import (
    claim_reliability,
    decision_confidence,
    effective_reliability,
    formality_ceiling,
    gamma,
)
from v1.core.ontology import BoundedContext, Claim, DecisionRecord, Evidence
from v1.core.validator import KnowledgeBase

NOW = datetime(2026, 6, 14)
FUTURE = "2026-12"
PAST = "2026-01"


def _ev(eid, claim, reliability, formality, valid_until=FUTURE, kind="empirical"):
    return Evidence(
        id=eid, kind=kind, target_claim_id=claim, claim_scope="scope",
        valid_from="2026-01", valid_until=valid_until,
        source="src", reliability=reliability, formality=formality,
    )


class TestGammaInvariants(unittest.TestCase):
    def test_wlnk_is_the_weak_link(self):
        self.assertEqual(gamma([0.9, 0.8, 0.6]), 0.6)

    def test_idem_duplicates_add_nothing(self):
        self.assertEqual(gamma([0.9, 0.9, 0.9]), 0.9)


class TestFormalityAndDecay(unittest.TestCase):
    def test_formality_caps_reliability(self):
        self.assertEqual(formality_ceiling("F0"), 0.70)
        ev = _ev("E1", "C1", reliability=0.95, formality="F0")
        self.assertEqual(effective_reliability(ev, NOW), 0.70)  # capped, not 0.95

    def test_expired_evidence_decays(self):
        ev = _ev("E1", "C1", reliability=0.9, formality="F3", valid_until=PAST)
        self.assertAlmostEqual(effective_reliability(ev, NOW), 0.7)  # 0.9 - 0.2 decay


class TestClaimReliability(unittest.TestCase):
    def test_unsupported_claim_is_capped(self):
        kb = KnowledgeBase()
        r, f = claim_reliability("C1", kb, NOW)
        self.assertEqual((r, f), (0.5, "F0"))

    def test_supported_claim_is_its_weakest_evidence(self):
        kb = KnowledgeBase(evidence={
            "E1": _ev("E1", "C1", 0.9, "F3"),
            "E2": _ev("E2", "C1", 0.6, "F2"),
        })
        r, _f = claim_reliability("C1", kb, NOW)
        self.assertEqual(r, 0.6)


class TestDecisionConfidence(unittest.TestCase):
    def _kb(self):
        return KnowledgeBase(
            contexts={"Ctx": BoundedContext(id="Ctx", invariants=["x"])},
            claims={
                "C1": Claim(id="C1", statement="strong", context_id="Ctx"),
                "C2": Claim(id="C2", statement="weak", context_id="Ctx"),
            },
            evidence={
                "E1": _ev("E1", "C1", 0.9, "F3"),  # strong support
                "E2": _ev("E2", "C2", 0.5, "F1"),  # weak support
            },
        )

    def test_score_is_the_weakest_claim(self):
        kb = self._kb()
        d = DecisionRecord(
            id="D1", context_id="Ctx", decision_subject="x",
            option_set=["a", "b"], choice_rule="r", chosen="a",
            supporting_claim_ids=["C1", "C2"],
        )
        conf = decision_confidence(d, kb, NOW)
        self.assertEqual(conf.score, 0.5)      # capped by the weak claim
        self.assertEqual(conf.weakest_link, "C2")
        self.assertEqual(conf.band, "medium")

    def test_stale_evidence_flags_the_decision(self):
        kb = self._kb()
        kb.evidence["E1"] = _ev("E1", "C1", 0.9, "F3", valid_until=PAST)  # expired
        d = DecisionRecord(
            id="D1", context_id="Ctx", decision_subject="x",
            option_set=["a", "b"], choice_rule="r", chosen="a",
            supporting_claim_ids=["C1", "C2"],
        )
        conf = decision_confidence(d, kb, NOW)
        self.assertTrue(conf.stale)

    def test_unsupported_decision_is_low(self):
        kb = self._kb()
        d = DecisionRecord(
            id="D1", context_id="Ctx", decision_subject="x",
            option_set=["a", "b"], choice_rule="r", chosen="a",
            supporting_claim_ids=[],
        )
        conf = decision_confidence(d, kb, NOW)
        self.assertEqual(conf.band, "low")


if __name__ == "__main__":
    unittest.main()
