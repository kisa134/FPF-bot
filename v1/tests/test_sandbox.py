"""Contract for the real (subprocess-isolated) sandbox.

Proves the reward signal has teeth: green tests -> PASS, red tests -> FAIL,
and anything that cannot be judged (hang) -> ABSTAIN (fail-closed, never PASS).
"""

from __future__ import annotations

import unittest

from v1.core import SandboxStatus, make_python_verifier, run_isolated_python


class TestIsolatedRun(unittest.TestCase):
    def test_passing_tests_yield_pass(self):
        artifact = "def add(a, b):\n    return a + b\n"
        check = "from artifact import add\nassert add(2, 3) == 5\nprint('ok')\n"
        res = run_isolated_python(artifact, check)
        self.assertEqual(res.status, SandboxStatus.PASS)

    def test_failing_tests_yield_fail(self):
        artifact = "def add(a, b):\n    return a - b  # bug\n"
        check = "from artifact import add\nassert add(2, 3) == 5\n"
        res = run_isolated_python(artifact, check)
        self.assertEqual(res.status, SandboxStatus.FAIL)

    def test_hang_is_abstain_not_pass(self):
        artifact = "x = 1\n"
        check = "while True:\n    pass\n"
        res = run_isolated_python(artifact, check, timeout_s=1.0, cpu_seconds=1)
        # fail-closed: an artifact that cannot be judged is never evidence
        self.assertNotEqual(res.status, SandboxStatus.PASS)
        self.assertIn(res.status, {SandboxStatus.ABSTAIN, SandboxStatus.FAIL})


class TestVerifierAdapter(unittest.TestCase):
    def test_missing_artifact_is_abstain(self):
        verify = make_python_verifier("assert True")
        self.assertEqual(verify(None).status, SandboxStatus.ABSTAIN)

    def test_verifier_runs_against_artifact_file(self):
        import tempfile
        from pathlib import Path

        verify = make_python_verifier(
            "from artifact import answer\nassert answer() == 42\n"
        )
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.artifact"
            p.write_text("def answer():\n    return 42\n", encoding="utf-8")
            self.assertEqual(verify(str(p)).status, SandboxStatus.PASS)


if __name__ == "__main__":
    unittest.main()
