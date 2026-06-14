"""Contract for the FPF-Swarm: Architect ↔ Censor debate with veto."""

from __future__ import annotations

import tempfile
import unittest

from v1.core.orchestrator import Task
from v1.policy.swarm import SwarmRunner
from v1.policy.swarm_demo import demo_swarm


class TestSwarmDebate(unittest.TestCase):
    def test_censor_vetoes_and_architect_revises_to_done(self):
        ds = demo_swarm()
        with tempfile.TemporaryDirectory() as d:
            runner = SwarmRunner(d, ds, ds)
            events = []
            res = runner.run(Task("t", "datastore for BTC telemetry"), on_event=events.append)

            vetoes = [e for e in events if e.action == "veto"]
            revises = [e for e in events if e.action == "revise"]
            commits = [e for e in events if e.action == "commit" and e.ok]

            self.assertGreaterEqual(len(vetoes), 2)   # vague claim + vague evidence
            self.assertGreaterEqual(len(revises), 2)  # architect fixed both
            self.assertTrue(res["ok"])
            self.assertEqual(res["committed"], 5)

            # a vetoed-then-revised object is the one that actually landed
            ids = {n.id for n in runner.orch.memory.graph.all_nodes()}
            self.assertIn("c_write", ids)
            self.assertIn("D1", ids)

    def test_censor_runs_before_the_mechanical_validator(self):
        # The vague-"fast" claim is structurally valid (non-empty statement) yet
        # the Censor still rejects it — semantic review precedes structural.
        ds = demo_swarm()
        with tempfile.TemporaryDirectory() as d:
            runner = SwarmRunner(d, ds, ds)
            events = []
            runner.run(Task("t"), on_event=events.append)
            first_veto = next(e for e in events if e.action == "veto")
            self.assertIn("falsifiable", first_veto.content.lower())


if __name__ == "__main__":
    unittest.main()
