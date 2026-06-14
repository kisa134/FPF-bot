"""Smoke test for the FPF Studio API (offline demo provider).

Skips cleanly if FastAPI / httpx are not installed, so the core suite still runs
in minimal environments.
"""

from __future__ import annotations

import json
import unittest

try:
    from fastapi.testclient import TestClient

    from v1.web.server import app

    _HAVE_WEB = True
except Exception:  # fastapi/httpx not installed
    _HAVE_WEB = False


@unittest.skipUnless(_HAVE_WEB, "fastapi/httpx not installed")
class TestStudio(unittest.TestCase):
    def setUp(self):
        self.c = TestClient(app)

    def test_run_streams_steps_and_builds_graph(self):
        rid = self.c.post(
            "/api/runs", json={"task": "pick a datastore", "provider": "demo"}
        ).json()["run_id"]

        done = None
        with self.c.stream("GET", f"/api/runs/{rid}/stream") as s:
            for line in s.iter_lines():
                if line.startswith("data: "):
                    ev = json.loads(line[6:])
                    if ev.get("type") == "done":
                        done = ev
        self.assertIsNotNone(done)
        self.assertTrue(done["ok"])
        self.assertEqual(done["final_phase"], "DONE")

        g = self.c.get(f"/api/runs/{rid}/graph").json()
        kinds = {n["kind"] for n in g["nodes"]}
        self.assertIn("DecisionRecord", kinds)
        rels = {e["rel"] for e in g["edges"]}
        self.assertIn("RELIES_ON", rels)

        obj = self.c.get(f"/api/runs/{rid}/object/D1").json()
        self.assertEqual(obj["kind"], "DecisionRecord")
        self.assertEqual(obj["payload"]["chosen"], "postgres")

    def test_ui_assets_served(self):
        self.assertEqual(self.c.get("/").status_code, 200)
        self.assertEqual(self.c.get("/app.js").status_code, 200)


if __name__ == "__main__":
    unittest.main()
