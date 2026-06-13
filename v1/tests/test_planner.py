"""Contract for the policy-driven planner.

Uses deterministic policies (no model, no network) to prove the planner
sequences a Policy through the protected loop: a good policy reaches DONE, a
self-correcting policy recovers after a rejection, and a hopeless policy aborts
cleanly instead of looping forever.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta
from typing import Any, Optional

from v1.core import Step, Task
from v1.core.validator import KnowledgeBase, Violation
from v1.policy import Planner, ScriptedPolicy

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


class TestHappyPath(unittest.TestCase):
    def test_scripted_policy_reaches_done(self):
        with tempfile.TemporaryDirectory() as d:
            planner = Planner(d, ScriptedPolicy(GOOD))
            res = planner.run(Task("t1", "pick a datastore"))
            self.assertTrue(res.ok, res.aborted_reason)
            self.assertEqual(res.final_step, Step.DONE)
            self.assertEqual(res.steps_taken, 4)
            self.assertTrue(all(s.ok for s in res.history))
            # memory actually persisted the run
            self.assertIsNotNone(planner.orch.memory.graph.get_node("D1"))


class _SelfCorrectingPolicy:
    """Emits a dangling Evidence first, then a valid one once given feedback."""

    def __init__(self) -> None:
        self.calls = 0

    def propose(self, *, kind, task, step, tool_schema, kb, feedback=None) -> dict[str, Any]:
        if kind != "Evidence":
            return GOOD[kind]
        self.calls += 1
        if feedback:  # corrected attempt
            return GOOD["Evidence"]
        bad = dict(GOOD["Evidence"])
        bad["target_claim_id"] = "ghost"  # references a non-existent claim
        return bad


class TestSelfCorrection(unittest.TestCase):
    def test_planner_feeds_violations_back_and_recovers(self):
        with tempfile.TemporaryDirectory() as d:
            policy = _SelfCorrectingPolicy()
            planner = Planner(d, policy, max_retries=2)
            res = planner.run(Task("t2"))
            self.assertTrue(res.ok, res.aborted_reason)
            self.assertEqual(res.final_step, Step.DONE)
            # one rejected Evidence attempt, then a successful one
            self.assertEqual(policy.calls, 2)
            rejected = [s for s in res.history if not s.ok]
            self.assertEqual(len(rejected), 1)
            self.assertEqual(rejected[0].violations[0].code, "DANGLING_CLAIM")


class _HopelessPolicy:
    """Always emits a structurally invalid Claim."""

    def propose(self, *, kind, task, step, tool_schema, kb, feedback=None) -> dict[str, Any]:
        if kind == "BoundedContext":
            return GOOD["BoundedContext"]
        return {"id": "C1", "statement": "", "context_id": "Proj.Alpha"}  # empty stmt


class TestAbort(unittest.TestCase):
    def test_planner_aborts_after_exhausting_retries(self):
        with tempfile.TemporaryDirectory() as d:
            planner = Planner(d, _HopelessPolicy(), max_retries=2)
            res = planner.run(Task("t3"))
            self.assertFalse(res.ok)
            self.assertIn("failed after 3 attempts", res.aborted_reason)
            # never advanced past the claim step
            self.assertEqual(res.final_step, Step.CLAIM)


class _FakeBlock:
    type = "tool_use"

    def __init__(self, payload):
        self.input = payload


class _FakeMessages:
    def __init__(self, payload):
        self._payload = payload
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return type("Resp", (), {"content": [_FakeBlock(self._payload)]})()


class _FakeClient:
    def __init__(self, payload):
        self.messages = _FakeMessages(payload)


class TestAnthropicPolicyShape(unittest.TestCase):
    """Exercise the real AnthropicPolicy.propose path with a stub client."""

    def test_forced_tool_use_is_parsed_and_request_is_well_formed(self):
        from v1.policy import AnthropicPolicy

        client = _FakeClient(GOOD["BoundedContext"])
        policy = AnthropicPolicy(client=client)
        out = policy.propose(
            kind="BoundedContext",
            task=Task("t", "demo"),
            step=Step.FRAME,
            tool_schema={"type": "object"},
            kb=KnowledgeBase(),
        )
        self.assertEqual(out, GOOD["BoundedContext"])
        # the request forced the correct single tool
        kw = client.messages.last_kwargs
        self.assertEqual(kw["model"], "claude-opus-4-8")
        self.assertEqual(kw["tool_choice"], {"type": "tool", "name": "declare_bounded_context"})
        self.assertEqual(kw["tools"][0]["name"], "declare_bounded_context")


if __name__ == "__main__":
    unittest.main()
