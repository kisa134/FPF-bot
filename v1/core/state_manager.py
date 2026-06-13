"""FPF reasoning state machine.

The orchestrator does not let the model "free-associate". It walks the model
through a fixed sequence of FPF moves, and each transition is *gated by the
validator*: you cannot advance until the current move has produced a
well-formed, reference-complete FPF object.

V1 loop (deliberately small):

    FRAME      -> a BoundedContext is declared (A.1.1)
    CLAIM      -> at least one Claim is asserted inside that frame
    EVIDENCE   -> Evidence is attached to a claim (A.2.4)
    DECISION   -> a DecisionRecord is recorded (C.11)
    DONE

Each step has an explicit set of object kinds it will accept. Submitting the
wrong kind for the current step is itself a (procedural) rejection -- the state
machine, not a prompt, enforces order.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .validator import KnowledgeBase, Violation, admit, validate


class Step(str, Enum):
    FRAME = "FRAME"
    CLAIM = "CLAIM"
    EVIDENCE = "EVIDENCE"
    DECISION = "DECISION"
    DONE = "DONE"


# Which object kinds may be submitted at each step, and where a successful
# submission moves next. The minimum count must be met before advancing.
_ACCEPTS: dict[Step, set[str]] = {
    Step.FRAME: {"BoundedContext"},
    Step.CLAIM: {"Claim"},
    Step.EVIDENCE: {"Evidence"},
    Step.DECISION: {"DecisionRecord"},
}
_NEXT: dict[Step, Step] = {
    Step.FRAME: Step.CLAIM,
    Step.CLAIM: Step.EVIDENCE,
    Step.EVIDENCE: Step.DECISION,
    Step.DECISION: Step.DONE,
}


@dataclass(frozen=True)
class SubmitOutcome:
    accepted: bool
    step_before: Step
    step_after: Step
    violations: list[Violation]


@dataclass
class StateManager:
    """Drives the FPF loop over a shared :class:`KnowledgeBase`."""

    kb: KnowledgeBase = field(default_factory=KnowledgeBase)
    step: Step = Step.FRAME

    def accepts(self) -> set[str]:
        """Object kinds the agent may legally submit right now."""
        return set(_ACCEPTS.get(self.step, set()))

    def submit(self, kind: str, raw: dict[str, Any]) -> SubmitOutcome:
        """Attempt one FPF move. Advances only on a fully valid object."""
        before = self.step

        if self.step is Step.DONE:
            return SubmitOutcome(
                accepted=False,
                step_before=before,
                step_after=before,
                violations=[
                    Violation(
                        code="LOOP_DONE",
                        object_kind=kind,
                        object_id=str(raw.get("id", "?")),
                        detail="reasoning loop already complete; nothing to submit",
                        spec_anchor="orchestrator",
                    )
                ],
            )

        if kind not in self.accepts():
            return SubmitOutcome(
                accepted=False,
                step_before=before,
                step_after=before,
                violations=[
                    Violation(
                        code="WRONG_STEP",
                        object_kind=kind,
                        object_id=str(raw.get("id", "?")),
                        detail=(
                            f"step {self.step.value} accepts {sorted(self.accepts())}, "
                            f"not {kind!r}"
                        ),
                        spec_anchor="orchestrator",
                    )
                ],
            )

        result = validate(kind, raw, self.kb)
        if not result.ok:
            return SubmitOutcome(
                accepted=False,
                step_before=before,
                step_after=before,
                violations=result.violations,
            )

        admit(result.parsed, self.kb)
        self.step = _NEXT[self.step]
        return SubmitOutcome(
            accepted=True,
            step_before=before,
            step_after=self.step,
            violations=[],
        )
