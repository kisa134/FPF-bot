"""FPF reasoning state machine — phased, branching.

The earlier V1 loop was a rigid line (one Claim, one Evidence, one Decision).
Real FPF work branches: many claims, evidence attached in any order, promises,
commitments, and methods interleaved, several decisions. So the machine now has
three phases:

    FRAME  -> at least one BoundedContext is declared (A.1.1)
    WORK   -> open phase: Claim / Evidence / PromiseContent / Commitment /
              Method / DecisionRecord / further BoundedContext, repeatable, in
              any referentially-valid order
    DONE   -> reached only by an explicit finish(), allowed once the work has
              produced at least one DecisionRecord (C.11)

Every move is still gated by the validator; the machine only decides *which
kinds* are legal now and *when finishing is allowed*. Choosing among the legal
moves (and choosing to finish) is the policy's job, not the machine's.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .validator import KnowledgeBase, Violation, admit, validate


class Step(str, Enum):
    FRAME = "FRAME"
    WORK = "WORK"
    DONE = "DONE"


# All object kinds that may be submitted during the open WORK phase.
_WORK_KINDS = {
    "BoundedContext",
    "Claim",
    "Evidence",
    "PromiseContent",
    "Commitment",
    "Method",
    "DecisionRecord",
}
_ACCEPTS: dict[Step, set[str]] = {
    Step.FRAME: {"BoundedContext"},
    Step.WORK: set(_WORK_KINDS),
}


@dataclass(frozen=True)
class SubmitOutcome:
    accepted: bool
    step_before: Step
    step_after: Step
    violations: list[Violation]


@dataclass
class StateManager:
    """Drives the phased FPF loop over a shared :class:`KnowledgeBase`."""

    kb: KnowledgeBase = field(default_factory=KnowledgeBase)
    step: Step = Step.FRAME

    #: Soft caps that force a bounded analysis to converge on a decision instead
    #: of a verbose model enumerating claims/evidence forever.
    MAX_CLAIMS = 6
    MAX_EVIDENCE = 4

    def accepts(self) -> set[str]:
        """Object kinds the agent may legally submit right now.

        The WORK phase narrows as the analysis matures so the agent must
        progress instead of looping: once a frame exists it cannot re-declare
        the context; past the claim/evidence caps those kinds drop out; and once
        a decision is recorded, nothing remains to submit — only finishing.
        """
        allowed = set(_ACCEPTS.get(self.step, set()))
        if self.step is Step.WORK:
            if self.kb.contexts:
                allowed.discard("BoundedContext")
            if len(self.kb.claims) >= self.MAX_CLAIMS:
                allowed.discard("Claim")
            if len(self.kb.evidence) >= self.MAX_EVIDENCE:
                allowed.discard("Evidence")
            if self.kb.decisions:
                allowed.clear()  # a decision exists → the only move left is finish
        return allowed

    def can_finish(self) -> bool:
        """Finishing is lawful once WORK has produced a decision (C.11)."""
        return self.step is Step.WORK and len(self.kb.decisions) >= 1

    def submit(self, kind: str, raw: dict[str, Any]) -> SubmitOutcome:
        """Attempt one FPF move. FRAME advances to WORK on a valid context;
        WORK is a fixed point (it stays open for more moves)."""
        before = self.step

        if self.step is Step.DONE:
            return self._reject(before, kind, raw, "LOOP_DONE", "loop already complete")

        if kind not in self.accepts():
            return self._reject(
                before,
                kind,
                raw,
                "WRONG_STEP",
                f"step {self.step.value} accepts {sorted(self.accepts())}, not {kind!r}",
            )

        result = validate(kind, raw, self.kb)
        if not result.ok:
            return SubmitOutcome(False, before, before, result.violations)

        admit(result.parsed, self.kb)
        if self.step is Step.FRAME:
            self.step = Step.WORK  # first frame opens the work phase
        return SubmitOutcome(True, before, self.step, [])

    def finish(self) -> SubmitOutcome:
        """Close the work phase. Only legal from WORK with a decision present."""
        before = self.step
        if not self.can_finish():
            return self._reject(
                before,
                "<finish>",
                {},
                "CANNOT_FINISH",
                "finishing requires WORK phase with at least one DecisionRecord (C.11)",
            )
        self.step = Step.DONE
        return SubmitOutcome(True, before, self.step, [])

    def _reject(
        self, before: Step, kind: str, raw: dict[str, Any], code: str, detail: str
    ) -> SubmitOutcome:
        return SubmitOutcome(
            False,
            before,
            before,
            [
                Violation(
                    code=code,
                    object_kind=kind,
                    object_id=str(raw.get("id", "?")),
                    detail=detail,
                    spec_anchor="orchestrator",
                )
            ],
        )
