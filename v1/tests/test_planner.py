"""Contract for the branching, policy-driven planner.

Deterministic policies (no model, no network) prove the planner sequences a
Policy through the protected branching loop: a good policy reaches DONE via an
explicit finish, a self-correcting policy recovers after a rejection, and a
hopeless policy aborts cleanly instead of looping forever.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta
from typing import Any

from v1.core import Step, Task
from v1.core.validator import KnowledgeBase
from v1.memory import LexicalSemanticIndex
from v1.policy import FINISH, Planner, ScriptedPolicy

NOW = datetime(2026, 6, 13)
LATER = NOW + timedelta(days=30)

GOOD = {
    "BoundedContext": {"id": "Proj.Alpha", "invariants": ["terms are local"]},
    "Claim": {"id": "C1", "statement": "X improves latency", "context_id": "Proj.Alpha"},
    "Evidence": {
        "id": "E1",
        "kind": "empirical",
        "target_claim_id": "C1",
        "claim_scope": "p95 latency, 2026-Q2",
        "timespan": {"valid_from": NOW.isoformat(), "valid_until": LATER.isoformat()},
        "source": "benchmark-417",
    },
    "DecisionRecord": {
        "id": "D1",
        "context_id": "Proj.Alpha",
        "decision_subject": "datastore",
        "option_set": ["postgres", "mysql"],
        "choice_rule": "lowest p95 under budget",
        "chosen": "postgres",
        "supporting_claim_ids": ["C1"],
    },
}
HAPPY = ["BoundedContext", "Claim", "Evidence", "DecisionRecord", FINISH]


class TestHappyPath(unittest.TestCase):
    def test_scripted_policy_reaches_done(self):
        with tempfile.TemporaryDirectory() as d:
            planner = Planner(d, ScriptedPolicy(HAPPY, GOOD))
            res = planner.run(Task("t1", "pick a datastore"))
            self.assertTrue(res.ok, res.aborted_reason)
            self.assertEqual(res.final_step, Step.DONE)
            self.assertEqual(res.steps_taken, 5)  # 4 objects + finish
            self.assertTrue(all(s.ok for s in res.history))
            self.assertIsNotNone(planner.orch.memory.graph.get_node("D1"))

    def test_planner_consults_semantic_recall(self):
        with tempfile.TemporaryDirectory() as d:
            planner = Planner(d, ScriptedPolicy(HAPPY, GOOD), semantic=LexicalSemanticIndex())
            res = planner.run(Task("t1", "datastore latency choice"))
            self.assertTrue(res.ok)
            # the claim's statement was indexed and is recallable
            self.assertIn("C1", planner.orch.memory.semantic.recall("latency", k=3))


class _SelfCorrectingPolicy:
    """Emits a dangling Evidence first, then a valid one once given feedback."""

    def __init__(self) -> None:
        self.evidence_calls = 0
        self._seq = ["BoundedContext", "Claim", "Evidence", "DecisionRecord", FINISH]
        self._i = 0

    def choose(self, *, allowed_kinds, can_finish, feedback=None, **_: Any):
        move = self._seq[self._i]
        if move == FINISH:
            self._i += 1
            return (FINISH, None)
        if move == "Evidence":
            self.evidence_calls += 1
            if not feedback:
                bad = dict(GOOD["Evidence"])
                bad["target_claim_id"] = "ghost"  # dangling
                return ("Evidence", bad)
        self._i += 1
        return (move, GOOD[move])


class TestSelfCorrection(unittest.TestCase):
    def test_planner_feeds_violations_back_and_recovers(self):
        with tempfile.TemporaryDirectory() as d:
            policy = _SelfCorrectingPolicy()
            planner = Planner(d, policy, max_retries=2)
            res = planner.run(Task("t2"))
            self.assertTrue(res.ok, res.aborted_reason)
            self.assertEqual(res.final_step, Step.DONE)
            self.assertEqual(policy.evidence_calls, 2)  # one bad, one corrected
            rejected = [s for s in res.history if not s.ok]
            self.assertEqual(len(rejected), 1)
            self.assertEqual(rejected[0].violations[0].code, "DANGLING_CLAIM")


class _HopelessPolicy:
    """Frames once, then always emits a structurally invalid Claim."""

    def choose(self, *, allowed_kinds, can_finish, **_: Any):
        if "BoundedContext" in allowed_kinds and allowed_kinds == {"BoundedContext"}:
            return ("BoundedContext", GOOD["BoundedContext"])
        return ("Claim", {"id": "C1", "statement": "", "context_id": "Proj.Alpha"})


class TestAbort(unittest.TestCase):
    def test_planner_aborts_after_exhausting_retries(self):
        with tempfile.TemporaryDirectory() as d:
            planner = Planner(d, _HopelessPolicy(), max_retries=2)
            res = planner.run(Task("t3"))
            self.assertFalse(res.ok)
            self.assertIn("failed after 3 attempts", res.aborted_reason)
            self.assertEqual(res.final_step, Step.WORK)  # framed, never closed


class _FakeBlock:
    type = "tool_use"

    def __init__(self, name, payload):
        self.name = name
        self.input = payload


class _FakeMessages:
    def __init__(self, name, payload):
        self._name = name
        self._payload = payload
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return type("Resp", (), {"content": [_FakeBlock(self._name, self._payload)]})()


class _FakeClient:
    def __init__(self, name, payload):
        self.messages = _FakeMessages(name, payload)


class TestAnthropicPolicyShape(unittest.TestCase):
    """Exercise the real AnthropicPolicy.choose path with a stub client."""

    def test_forced_tool_use_is_parsed_and_request_is_well_formed(self):
        from v1.policy import AnthropicPolicy

        client = _FakeClient("declare_bounded_context", GOOD["BoundedContext"])
        policy = AnthropicPolicy(client=client)
        kind, raw = policy.choose(
            task=Task("t", "demo"),
            step=Step.FRAME,
            allowed_kinds={"BoundedContext"},
            can_finish=False,
            kb=KnowledgeBase(),
        )
        self.assertEqual((kind, raw), ("BoundedContext", GOOD["BoundedContext"]))
        kw = client.messages.last_kwargs
        self.assertEqual(kw["model"], "claude-opus-4-8")
        self.assertEqual(kw["tool_choice"], {"type": "any"})
        self.assertEqual([t["name"] for t in kw["tools"]], ["declare_bounded_context"])

    def test_finish_tool_offered_when_allowed(self):
        from v1.policy import AnthropicPolicy

        client = _FakeClient("finish_reasoning", {})
        policy = AnthropicPolicy(client=client)
        kind, raw = policy.choose(
            task=Task("t"),
            step=Step.WORK,
            allowed_kinds={"Claim"},
            can_finish=True,
            kb=KnowledgeBase(),
        )
        self.assertEqual(kind, FINISH)
        names = [t["name"] for t in client.messages.last_kwargs["tools"]]
        self.assertIn("finish_reasoning", names)


if __name__ == "__main__":
    unittest.main()
