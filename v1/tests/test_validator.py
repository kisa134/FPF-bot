"""Executable contract for the FPF validator and state machine.

Each test pins one FPF invariant to a concrete spec anchor. The "rejects"
tests are as important as the "accepts" ones: they prove the gatekeeper is
actually closed, not just permissive.

Run: python -m pytest v1/tests -q   (or: python -m unittest)
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from v1.core import (
    BoundedContext,
    Evidence,
    EvidenceKind,
    KnowledgeBase,
    StateManager,
    Step,
    Timespan,
    validate,
    validate_batch,
)

NOW = datetime(2026, 6, 13)
LATER = NOW + timedelta(days=30)


def _ctx(cid: str = "Proj.Alpha") -> dict:
    return {"id": cid, "invariants": ["terms are local to this frame"]}


def _claim(cid: str = "C1", context: str = "Proj.Alpha") -> dict:
    return {"id": cid, "statement": "X improves latency", "context_id": context}


def _evidence_empirical(eid: str = "E1", claim: str = "C1") -> dict:
    return {
        "id": eid,
        "kind": "empirical",
        "target_claim_id": claim,
        "claim_scope": "p95 latency on prod traffic, 2026-Q2",
        "timespan": {"valid_from": NOW.isoformat(), "valid_until": LATER.isoformat()},
        "source": "benchmark-run-417",
    }


class TestIntraObjectInvariants(unittest.TestCase):
    """Layer 1: invariants enforced by the ontology types (A.2.4, C.11)."""

    def test_evidence_requires_claim_scope(self):
        kb = KnowledgeBase(contexts={"Proj.Alpha": BoundedContext(**_ctx())})
        kb.claims["C1"] = _admit_claim(kb)
        bad = _evidence_empirical()
        del bad["claim_scope"]  # A.2.4: claim-scope is mandatory
        res = validate("Evidence", bad, kb)
        self.assertFalse(res.ok)
        self.assertEqual(res.violations[0].code, "SCHEMA")
        self.assertEqual(res.violations[0].spec_anchor, "A.2.4")

    def test_empirical_evidence_requires_horizon(self):
        kb = KnowledgeBase(contexts={"Proj.Alpha": BoundedContext(**_ctx())})
        kb.claims["C1"] = _admit_claim(kb)
        bad = _evidence_empirical()
        bad["timespan"] = {"valid_from": NOW.isoformat()}  # open-ended empirical
        res = validate("Evidence", bad, kb)
        self.assertFalse(res.ok)
        self.assertEqual(res.violations[0].spec_anchor, "A.2.4")

    def test_deductive_evidence_may_be_open_ended(self):
        kb = KnowledgeBase(contexts={"Proj.Alpha": BoundedContext(**_ctx())})
        kb.claims["C1"] = _admit_claim(kb)
        ev = _evidence_empirical()
        ev["kind"] = "deductive"
        ev["timespan"] = {"valid_from": NOW.isoformat()}  # ok for a proof
        res = validate("Evidence", ev, kb)
        self.assertTrue(res.ok, res.violations)

    def test_decision_chosen_must_be_in_option_set(self):
        kb = KnowledgeBase(contexts={"Proj.Alpha": BoundedContext(**_ctx())})
        bad = {
            "id": "D1",
            "context_id": "Proj.Alpha",
            "decision_subject": "datastore",
            "option_set": ["postgres", "mysql"],
            "choice_rule": "lowest p95 under budget",
            "chosen": "sqlite",  # C.11: ChoiceResult must be in OptionSet
        }
        res = validate("DecisionRecord", bad, kb)
        self.assertFalse(res.ok)
        self.assertEqual(res.violations[0].spec_anchor, "C.11")

    def test_decision_needs_two_options(self):
        kb = KnowledgeBase(contexts={"Proj.Alpha": BoundedContext(**_ctx())})
        bad = {
            "id": "D1",
            "context_id": "Proj.Alpha",
            "decision_subject": "datastore",
            "option_set": ["postgres"],  # no real choice
            "choice_rule": "x",
            "chosen": "postgres",
        }
        res = validate("DecisionRecord", bad, kb)
        self.assertFalse(res.ok)


class TestInterObjectInvariants(unittest.TestCase):
    """Layer 2: referential integrity (A.1.1 1..1, A.2.4 target claim)."""

    def test_claim_with_undeclared_context_is_dangling(self):
        kb = KnowledgeBase()  # no contexts declared
        res = validate("Claim", _claim(), kb)
        self.assertFalse(res.ok)
        self.assertEqual(res.violations[0].code, "DANGLING_CONTEXT")
        self.assertEqual(res.violations[0].spec_anchor, "A.1.1")

    def test_evidence_for_undeclared_claim_is_dangling(self):
        kb = KnowledgeBase(contexts={"Proj.Alpha": BoundedContext(**_ctx())})
        res = validate("Evidence", _evidence_empirical(claim="ghost"), kb)
        self.assertFalse(res.ok)
        self.assertEqual(res.violations[0].code, "DANGLING_CLAIM")

    def test_well_formed_chain_is_accepted(self):
        kb = KnowledgeBase()
        violations = validate_batch(
            [
                ("BoundedContext", _ctx()),
                ("Claim", _claim()),
                ("Evidence", _evidence_empirical()),
            ],
            kb,
        )
        self.assertEqual(violations, [], [str(v) for v in violations])
        self.assertIn("C1", kb.claims)
        self.assertIn("E1", kb.evidence)


def _decision():
    return {
        "id": "D1",
        "context_id": "Proj.Alpha",
        "decision_subject": "datastore",
        "option_set": ["postgres", "mysql"],
        "choice_rule": "lowest p95 under budget",
        "chosen": "postgres",
        "supporting_claim_ids": ["C1"],
    }


class TestStateMachine(unittest.TestCase):
    """The phased loop enforces FPF structure, not a prompt."""

    def test_cannot_claim_before_framing(self):
        sm = StateManager()
        self.assertEqual(sm.step, Step.FRAME)
        out = sm.submit("Claim", _claim())  # FRAME accepts only BoundedContext
        self.assertFalse(out.accepted)
        self.assertEqual(out.violations[0].code, "WRONG_STEP")
        self.assertEqual(sm.step, Step.FRAME)

    def test_work_phase_is_open_and_repeatable(self):
        sm = StateManager()
        self.assertTrue(sm.submit("BoundedContext", _ctx()).accepted)
        self.assertEqual(sm.step, Step.WORK)  # framing opens WORK
        # WORK accepts many kinds, in any order, repeatably
        self.assertTrue(sm.submit("Claim", _claim("C1")).accepted)
        self.assertTrue(sm.submit("Claim", _claim("C2")).accepted)
        self.assertTrue(sm.submit("Evidence", _evidence_empirical("E1", "C2")).accepted)
        self.assertEqual(sm.step, Step.WORK)  # stays open

    def test_finish_requires_a_decision(self):
        sm = StateManager()
        sm.submit("BoundedContext", _ctx())
        sm.submit("Claim", _claim())
        self.assertFalse(sm.can_finish())
        self.assertFalse(sm.finish().accepted)  # no decision yet
        self.assertTrue(sm.submit("DecisionRecord", _decision()).accepted)
        self.assertTrue(sm.can_finish())
        self.assertTrue(sm.finish().accepted)
        self.assertEqual(sm.step, Step.DONE)

    def test_promise_commitment_method_flow(self):
        sm = StateManager()
        sm.submit("BoundedContext", _ctx())
        self.assertTrue(
            sm.submit(
                "PromiseContent",
                {"id": "P1", "context_id": "Proj.Alpha", "statement": "ship by Q3"},
            ).accepted
        )
        self.assertTrue(
            sm.submit(
                "Commitment",
                {
                    "id": "K1",
                    "context_id": "Proj.Alpha",
                    "promise_content_id": "P1",
                    "debtor": "team",
                    "creditor": "user",
                },
            ).accepted
        )
        # a commitment to an undeclared promise is rejected
        bad = sm.submit(
            "Commitment",
            {
                "id": "K2",
                "context_id": "Proj.Alpha",
                "promise_content_id": "ghost",
                "debtor": "team",
                "creditor": "user",
            },
        )
        self.assertFalse(bad.accepted)
        self.assertEqual(bad.violations[0].code, "DANGLING_PROMISE")


def _admit_claim(kb: KnowledgeBase):
    from v1.core import Claim

    c = Claim(**_claim())
    return c


if __name__ == "__main__":
    unittest.main()
