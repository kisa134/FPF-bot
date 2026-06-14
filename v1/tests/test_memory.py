"""Executable contract for the three-layer memory.

Pins the behaviours the design promises: lossless Markdown round-trip, the
graph's ontology firewall (it must reject illegal relations), the trajectory
timeline, and Git checkpoint/reset amnesia protection.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from v1.core import BoundedContext, Claim, DecisionRecord, Evidence
from v1.memory import MarkdownStore, MemoryStore, OntologyError, ReasoningGraph

NOW = datetime(2026, 6, 13)
LATER = NOW + timedelta(days=30)


def _ctx():
    return BoundedContext(id="Proj.Alpha", invariants=["terms are local"])


def _claim():
    return Claim(id="C1", statement="X improves latency", context_id="Proj.Alpha")


def _evidence():
    return Evidence(
        id="E1",
        kind="empirical",
        target_claim_id="C1",
        claim_scope="p95 latency, 2026-Q2",
        valid_from=NOW.isoformat(), valid_until=LATER.isoformat(),
        source="benchmark-417",
    )


def _decision():
    return DecisionRecord(
        id="D1",
        context_id="Proj.Alpha",
        decision_subject="datastore",
        option_set=["postgres", "mysql"],
        choice_rule="lowest p95 under budget",
        chosen="postgres",
        supporting_claim_ids=["C1"],
    )


class TestMarkdownRoundTrip(unittest.TestCase):
    def test_evidence_round_trips_losslessly(self):
        with tempfile.TemporaryDirectory() as d:
            md = MarkdownStore(d)
            path = md.write(_evidence())
            back = md.read(path)
            self.assertEqual(back, _evidence())  # frozen models compare by value

    def test_load_all_recovers_working_set(self):
        with tempfile.TemporaryDirectory() as d:
            md = MarkdownStore(d)
            md.write(_ctx())
            md.write(_claim())
            loaded = {type(o).__name__ for o in md.load_all()}
            self.assertEqual(loaded, {"BoundedContext", "Claim"})


class TestGraphFirewall(unittest.TestCase):
    def test_supports_edge_to_nonclaim_is_rejected(self):
        g = ReasoningGraph()
        g.add_node("Proj.Alpha", "BoundedContext")
        g.add_node("E1", "Evidence", context_id="Proj.Alpha")
        # Evidence may only SUPPORT a Claim, never a BoundedContext.
        with self.assertRaises(OntologyError):
            g.add_edge("E1", "Proj.Alpha", "SUPPORTS")

    def test_edge_to_missing_node_is_rejected(self):
        g = ReasoningGraph()
        g.add_node("C1", "Claim", context_id="Proj.Alpha")
        with self.assertRaises(OntologyError):
            g.add_edge("C1", "ghost", "IN_CONTEXT")

    def test_legal_edges_and_neighbors(self):
        g = ReasoningGraph()
        g.add_node("Proj.Alpha", "BoundedContext")
        g.add_node("C1", "Claim", context_id="Proj.Alpha")
        g.add_node("E1", "Evidence", context_id="Proj.Alpha")
        g.add_edge("C1", "Proj.Alpha", "IN_CONTEXT")
        g.add_edge("E1", "C1", "SUPPORTS")
        # Who supports C1? -> E1 (incoming SUPPORTS).
        supporters = g.neighbors("C1", rel="SUPPORTS", incoming=True)
        self.assertEqual([n.id for n in supporters], ["E1"])


class TestMemoryStore(unittest.TestCase):
    def test_remember_persists_all_layers_and_trajectory(self):
        with tempfile.TemporaryDirectory() as d:
            store = MemoryStore(d, db_path=":memory:")
            store.remember(_ctx())
            store.remember(_claim())
            store.remember(_evidence())
            store.remember(_decision())

            # structural: edges were derived from the objects' own fields
            sup = store.graph.neighbors("C1", rel="SUPPORTS", incoming=True)
            self.assertEqual([n.id for n in sup], ["E1"])
            relies = store.graph.neighbors("D1", rel="RELIES_ON")
            self.assertEqual([n.id for n in relies], ["C1"])

            # timeline: one accepted trajectory entry per remembered object
            traj = store.graph.trajectory()
            self.assertEqual(len(traj), 4)
            self.assertTrue(all(e.status == "accepted" for e in traj))
            self.assertEqual(traj[1].object_id, "C1")

            # epistemic: markdown file exists on disk
            self.assertTrue((Path(d) / "epistemic" / "Claim" / "C1.md").exists())

    def test_remember_rejects_evidence_for_unknown_claim(self):
        with tempfile.TemporaryDirectory() as d:
            store = MemoryStore(d, db_path=":memory:")
            store.remember(_ctx())
            # No claim C1 in the graph -> SUPPORTS edge has no target node.
            ev = Evidence(
                id="E9",
                kind="deductive",
                target_claim_id="C1",
                claim_scope="scope",
                valid_from=NOW.isoformat(),
                source="proof",
            )
            with self.assertRaises(OntologyError):
                store.remember(ev)


class TestGitCheckpoint(unittest.TestCase):
    def test_reset_restores_sane_state(self):
        with tempfile.TemporaryDirectory() as d:
            store = MemoryStore(d, db_path=":memory:")
            store.init_repo()
            store.git("config", "user.email", "agent@fpf.local")
            store.git("config", "user.name", "fpf-agent")
            store.git("config", "commit.gpgsign", "false")  # isolated memory repo
            store.remember(_ctx())
            store.remember(_claim())
            sane = store.checkpoint("sane: frame + claim")

            # Agent goes off the rails and deletes its working memory.
            (Path(d) / "epistemic" / "Claim" / "C1.md").unlink()
            self.assertFalse((Path(d) / "epistemic" / "Claim" / "C1.md").exists())

            store.reset_to(sane)  # snap back to the last sane reasoning state
            self.assertTrue((Path(d) / "epistemic" / "Claim" / "C1.md").exists())


if __name__ == "__main__":
    unittest.main()
