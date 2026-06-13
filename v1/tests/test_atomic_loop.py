"""Integration contract for the Atomic Cognitive Step.

Simulates the two cases that matter:

1. A successful step -> a git commit appears, the graph/trajectory gain rows,
   and the state machine advances.
2. A failed step (sandbox reward == 0) -> the filesystem AND SQLite return to
   their pre-step state, as if the step never happened, and the loop does not
   advance.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta

from v1.core import Orchestrator, Step, Task
from v1.core.sandbox import SandboxResult, SandboxStatus

NOW = datetime(2026, 6, 13)
LATER = NOW + timedelta(days=30)

PASS = lambda path: SandboxResult(SandboxStatus.PASS, "ok")
FAIL = lambda path: SandboxResult(SandboxStatus.FAIL, "tests red, reward=0")


def _ctx_raw():
    return {"id": "Proj.Alpha", "invariants": ["terms are local"]}


def _claim_raw():
    return {"id": "C1", "statement": "X improves latency", "context_id": "Proj.Alpha"}


def _evidence_raw():
    return {
        "id": "E1",
        "kind": "empirical",
        "target_claim_id": "C1",
        "claim_scope": "p95 latency, 2026-Q2",
        "timespan": {"valid_from": NOW.isoformat(), "valid_until": LATER.isoformat()},
        "source": "benchmark-417",
    }


def _frame_and_claim(orch: Orchestrator) -> None:
    assert orch.commit_step(
        "BoundedContext", _ctx_raw(), task=Task("t0", "frame")
    ).ok
    assert orch.commit_step("Claim", _claim_raw(), task=Task("t1", "assert claim")).ok


class TestSuccessfulStep(unittest.TestCase):
    def test_step_commits_and_advances(self):
        with tempfile.TemporaryDirectory() as d:
            orch = Orchestrator(d)
            init_sha = orch.last_good_sha

            res = orch.commit_step(
                "BoundedContext",
                _ctx_raw(),
                task=Task("t0", "frame the project"),
                thought="We are deciding the datastore for Proj.Alpha.",
                verify=PASS,
            )

            self.assertTrue(res.ok, res.violations)
            self.assertEqual(res.step_before, Step.FRAME)
            self.assertEqual(res.step_after, Step.CLAIM)  # advanced
            self.assertNotEqual(res.sha, init_sha)  # a new commit exists
            self.assertEqual(orch.last_good_sha, res.sha)

            # structural memory recorded it
            self.assertIsNotNone(orch.memory.graph.get_node("Proj.Alpha"))
            traj = orch.memory.graph.trajectory()
            self.assertEqual(len(traj), 1)
            self.assertEqual(traj[0].object_id, "Proj.Alpha")

    def test_full_chain_walks_to_decision(self):
        with tempfile.TemporaryDirectory() as d:
            orch = Orchestrator(d)
            _frame_and_claim(orch)
            self.assertTrue(
                orch.commit_step("Evidence", _evidence_raw(), task=Task("t2"), verify=PASS).ok
            )
            decision = {
                "id": "D1",
                "context_id": "Proj.Alpha",
                "decision_subject": "datastore",
                "option_set": ["postgres", "mysql"],
                "choice_rule": "lowest p95 under budget",
                "chosen": "postgres",
                "supporting_claim_ids": ["C1"],
            }
            res = orch.commit_step("DecisionRecord", decision, task=Task("t3"), verify=PASS)
            self.assertTrue(res.ok)
            self.assertEqual(orch.step, Step.DONE)
            # decision relies on the claim, structurally
            relies = orch.memory.graph.neighbors("D1", rel="RELIES_ON")
            self.assertEqual([n.id for n in relies], ["C1"])


class TestFailedStepRollback(unittest.TestCase):
    def test_reward_zero_rolls_back_filesystem_and_sqlite(self):
        with tempfile.TemporaryDirectory() as d:
            orch = Orchestrator(d)
            _frame_and_claim(orch)

            sane_sha = orch.last_good_sha
            traj_before = len(orch.memory.graph.trajectory())
            step_before = orch.step  # EVIDENCE

            # The agent proposes a valid Evidence object, but its artifact fails
            # the sandbox (reward == 0).
            res = orch.commit_step(
                "Evidence",
                _evidence_raw(),
                task=Task("t2", "attach evidence"),
                thought="benchmark says p95 dropped",
                artifact="def bench(): assert False  # broken",
                verify=FAIL,
            )

            self.assertFalse(res.ok)
            self.assertTrue(res.rolled_back)
            self.assertEqual(res.verification.status, SandboxStatus.FAIL)

            # state machine did NOT advance
            self.assertEqual(orch.step, step_before)
            # git HEAD is back at the last sane checkpoint
            self.assertEqual(orch.last_good_sha, sane_sha)
            self.assertEqual(orch.memory.git("rev-parse", "HEAD"), sane_sha)
            # SQLite: the evidence node is gone, trajectory unchanged
            self.assertIsNone(orch.memory.graph.get_node("E1"))
            self.assertEqual(len(orch.memory.graph.trajectory()), traj_before)
            # filesystem: the hallucinated markdown + artifact were wiped
            self.assertFalse(
                (orch.memory.root / "epistemic" / "Evidence" / "E1.md").exists()
            )
            self.assertFalse((orch.memory.root / "artifacts" / "E1.artifact").exists())

            # ...and the agent can still make the *correct* move afterwards
            self.assertTrue(
                orch.commit_step("Evidence", _evidence_raw(), task=Task("t2b"), verify=PASS).ok
            )
            self.assertEqual(orch.step, Step.DECISION)

    def test_wrong_step_does_not_touch_memory(self):
        with tempfile.TemporaryDirectory() as d:
            orch = Orchestrator(d)
            # Submitting a Claim while still in FRAME is rejected pre-flight.
            res = orch.commit_step("Claim", _claim_raw(), task=Task("x"), verify=PASS)
            self.assertFalse(res.ok)
            self.assertEqual(res.violations[0].code, "WRONG_STEP")
            self.assertFalse(res.rolled_back)
            self.assertIsNone(orch.memory.graph.get_node("C1"))
            self.assertEqual(len(orch.memory.graph.trajectory()), 0)


if __name__ == "__main__":
    unittest.main()
