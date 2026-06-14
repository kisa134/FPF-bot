"""Smoke test for the CLI entrypoint (offline demo mode)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from v1.__main__ import main


class TestCli(unittest.TestCase):
    def test_demo_run_reaches_done(self):
        with tempfile.TemporaryDirectory() as d:
            code = main(["run", "pick a datastore", "--demo", "--memory", d])
            self.assertEqual(code, 0)
            # the run persisted a reasoning graph + markdown to the memory dir
            self.assertTrue((Path(d) / "graph.db").exists())
            self.assertTrue(
                (Path(d) / "epistemic" / "DecisionRecord" / "D1.md").exists()
            )


if __name__ == "__main__":
    unittest.main()
