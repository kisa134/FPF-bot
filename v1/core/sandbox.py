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

from dataclasses import dataclass
from enum import Enum
from typing import Callable


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
        # NOTE: real isolation boundary goes here (subprocess/container).
        return check(payload)
