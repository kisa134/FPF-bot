"""Smoke test for the FPF Swarm studio API (offline demo).

Skips cleanly if FastAPI / httpx are not installed.
"""

from __future__ import annotations

import json
import unittest

try:
    from fastapi.testclient import TestClient

    from v1.web.server import app

    _HAVE_WEB = True
except Exception:
    _HAVE_WEB = False


@unittest.skipUnless(_HAVE_WEB, "fastapi/httpx not installed")
class TestSwarmStudio(unittest.TestCase):
    def setUp(self):
        self.c = TestClient(app)

    def test_team_debate_streams_and_commits(self):
        rid = self.c.post("/api/runs", json={"task": "datastore for BTC", "provider": "demo"}).json()["run_id"]

        events, done = [], None
        with self.c.stream("GET", f"/api/runs/{rid}/stream") as s:
            for line in s.iter_lines():
                if line.startswith("data: "):
                    ev = json.loads(line[6:])
                    if ev.get("type") == "agent":
                        events.append(ev)
                    elif ev.get("type") == "done":
                        done = ev

        actions = [e["action"] for e in events]
        agents = {e["agent"] for e in events}
        self.assertIn("Architect", agents)
        self.assertIn("Censor", agents)
        self.assertIn("veto", actions)     # the censor actually pushed back
        self.assertIn("revise", actions)   # the architect corrected
        self.assertIn("commit", actions)

        self.assertIsNotNone(done)
        self.assertTrue(done["ok"])
        self.assertGreaterEqual(done["committed"], 4)

        g = self.c.get(f"/api/runs/{rid}/graph").json()
        self.assertIn("DecisionRecord", {n["kind"] for n in g["nodes"]})

    def test_ui_assets(self):
        self.assertEqual(self.c.get("/").status_code, 200)
        self.assertEqual(self.c.get("/app.js").status_code, 200)


if __name__ == "__main__":
    unittest.main()
