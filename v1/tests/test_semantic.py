"""Contract for the lexical semantic layer and its wiring into MemoryStore."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime

from v1.core import BoundedContext, Claim
from v1.memory import LexicalSemanticIndex, MemoryStore

NOW = datetime(2026, 6, 13)


class TestLexicalRecall(unittest.TestCase):
    def test_recall_ranks_relevant_first(self):
        idx = LexicalSemanticIndex()
        idx.index("C1", "postgres datastore latency benchmark p95")
        idx.index("C2", "frontend button color accessibility contrast")
        idx.index("C3", "datastore replication failover latency")
        hits = idx.recall("latency datastore", k=2)
        self.assertEqual(set(hits), {"C1", "C3"})
        self.assertNotIn("C2", hits)

    def test_empty_query_or_index_returns_nothing(self):
        idx = LexicalSemanticIndex()
        self.assertEqual(idx.recall("anything"), [])
        idx.index("C1", "something")
        self.assertEqual(idx.recall("the a an"), [])  # all stopwords

    def test_reindex_does_not_double_count(self):
        idx = LexicalSemanticIndex()
        idx.index("C1", "latency")
        idx.index("C1", "throughput")  # overwrite
        self.assertEqual(idx.recall("latency"), [])
        self.assertEqual(idx.recall("throughput"), ["C1"])


class TestMemoryStoreWiring(unittest.TestCase):
    def test_remembering_indexes_for_recall(self):
        with tempfile.TemporaryDirectory() as d:
            store = MemoryStore(d, db_path=":memory:", semantic=LexicalSemanticIndex())
            store.remember(BoundedContext(id="Proj.Alpha", invariants=["local terms"]))
            store.remember(
                Claim(
                    id="C1",
                    statement="postgres reduces tail latency under load",
                    context_id="Proj.Alpha",
                )
            )
            # the claim's statement is what gets indexed (see store._summ)
            self.assertEqual(store.semantic.recall("tail latency", k=1), ["C1"])


if __name__ == "__main__":
    unittest.main()
