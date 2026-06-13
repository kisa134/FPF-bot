"""Isolated verification of artifacts produced under FPF reasoning.

When the agent emits a *work artifact* (code, a derivation script, a check),
FPF's evidence discipline (A.2.4) says the claim it supports must be checkable,
not merely asserted. The sandbox is where an artifact is run against external
tests so its result can become empirical Evidence rather than a bare promise.

V1 is a deliberate STUB with a real, stable interface. It does not yet execute
untrusted code -- isolation (subprocess/container/seccomp) is intentionally
left as a single, well-marked seam so the rest of the orchestrator can be built
and tested against the contract today.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Optional


class SandboxStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    ABSTAIN = "abstain"  # could not run -> must NOT be read as evidence (fail-closed)


@dataclass(frozen=True)
class SandboxResult:
    status: SandboxStatus
    detail: str


# An external check takes the artifact payload and returns a result.
ExternalCheck = Callable[[str], SandboxResult]


class Sandbox:
    """Runs artifacts through registered external checks.

    Fail-closed: with no check for an artifact, the result is ABSTAIN, never
    PASS. Absence of disproof is not evidence (A.2.4).
    """

    def __init__(self) -> None:
        self._checks: dict[str, ExternalCheck] = {}

    def register(self, artifact_kind: str, check: ExternalCheck) -> None:
        self._checks[artifact_kind] = check

    def run(self, artifact_kind: str, payload: str) -> SandboxResult:
        check = self._checks.get(artifact_kind)
        if check is None:
            return SandboxResult(
                status=SandboxStatus.ABSTAIN,
                detail=f"no external check registered for {artifact_kind!r} (fail-closed)",
            )
        return check(payload)


# --------------------------------------------------------------------------- #
# Real isolation: run an artifact's tests in a separate, resource-capped process
# --------------------------------------------------------------------------- #
def _apply_limits(cpu_seconds: int, mem_bytes: int) -> Optional[Callable[[], None]]:
    """Build a POSIX preexec_fn that caps CPU and address space.

    Returns None on platforms without ``resource`` (e.g. Windows); the
    subprocess timeout still bounds wall-clock there.
    """
    try:
        import resource
    except ImportError:  # pragma: no cover - non-POSIX
        return None

    def _limit() -> None:  # pragma: no cover - runs in the child process
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
        if mem_bytes:
            resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
        os.setsid()  # isolate into its own process group

    return _limit


def run_isolated_python(
    artifact_code: str,
    test_code: str,
    *,
    timeout_s: float = 10.0,
    cpu_seconds: int = 5,
    mem_mb: int = 512,
) -> SandboxResult:
    """Execute ``test_code`` against ``artifact_code`` in an isolated process.

    The artifact is written as ``artifact.py`` and the test as ``check.py`` in a
    throwaway temp dir; the test imports the artifact module. Mapping:
        exit 0        -> PASS   (tests green, reward 1)
        exit non-zero -> FAIL   (tests red, reward 0)
        timeout/spawn -> ABSTAIN (could not judge; fail-closed, reward 0)

    Fail-closed is the rule: an artifact that hangs or cannot be run is NEVER
    treated as evidence (A.2.4).
    """
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "artifact.py").write_text(artifact_code, encoding="utf-8")
        (root / "check.py").write_text(test_code, encoding="utf-8")
        try:
            proc = subprocess.run(
                [sys.executable, "-S", "check.py"],  # -S: no site; minimal env below
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=timeout_s,
                preexec_fn=_apply_limits(cpu_seconds, mem_mb * 1024 * 1024),
                # Minimal environment: only the temp dir on the path, no inherited
                # PYTHONPATH/venv. Resource limits + timeout bound the process.
                env={
                    "PYTHONPATH": str(root),
                    "PATH": os.environ.get("PATH", ""),
                    "HOME": str(root),
                },
            )
        except subprocess.TimeoutExpired:
            return SandboxResult(
                SandboxStatus.ABSTAIN, f"timed out after {timeout_s}s (fail-closed)"
            )
        except Exception as exc:  # spawn failure -> cannot judge
            return SandboxResult(SandboxStatus.ABSTAIN, f"could not run: {exc}")

        if proc.returncode == 0:
            return SandboxResult(SandboxStatus.PASS, (proc.stdout or "tests passed").strip())
        tail = (proc.stderr or proc.stdout or "").strip()[-500:]
        return SandboxResult(SandboxStatus.FAIL, f"exit {proc.returncode}: {tail}")


def make_python_verifier(
    test_code: str, **limits
) -> Callable[[Optional[str]], SandboxResult]:
    """Adapt :func:`run_isolated_python` to the Orchestrator verifier signature.

    The returned callable receives the artifact file path written by the
    orchestrator, loads its code, and runs ``test_code`` against it in isolation.
    A missing artifact path is fail-closed (ABSTAIN): there is nothing to verify.
    """

    def _verify(artifact_path: Optional[str]) -> SandboxResult:
        if artifact_path is None or not Path(artifact_path).exists():
            return SandboxResult(
                SandboxStatus.ABSTAIN, "no artifact to verify (fail-closed)"
            )
        code = Path(artifact_path).read_text(encoding="utf-8")
        return run_isolated_python(code, test_code, **limits)

    return _verify
