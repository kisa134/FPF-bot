"""Planner: drives the atomic loop with a Policy until the task is done.

This is the first place a real reasoning *policy* (a model) enters the protected
loop. The planner asks the policy for the next FPF object, runs it through the
orchestrator's atomic ``commit_step``, and on rejection feeds the violations
back to the policy for a bounded number of retries. The orchestrator still owns
all safety — the planner only sequences intent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..core.orchestrator import Orchestrator, StepResult, Task, Verifier
from ..core.state_manager import Step
from ..tools.mcp_schema import tool_schemas
from .policy import Policy

# tool name -> input_schema, built once from the ontology types.
_SCHEMAS = {t["name"]: t["input_schema"] for t in tool_schemas()}
_KIND_TO_TOOL = {
    "BoundedContext": "declare_bounded_context",
    "Claim": "submit_claim",
    "Evidence": "attach_evidence",
    "DecisionRecord": "record_decision",
}


@dataclass
class PlanResult:
    ok: bool
    final_step: Step
    steps_taken: int
    history: list[StepResult] = field(default_factory=list)
    aborted_reason: Optional[str] = None


class Planner:
    """Sequences a Policy through the FPF loop on a fresh Orchestrator."""

    def __init__(
        self,
        memory_root: str | Path,
        policy: Policy,
        *,
        agent: str = "planner",
        max_retries: int = 2,
        max_steps: int = 12,
    ) -> None:
        self.orch = Orchestrator(memory_root, agent=agent)
        self.policy = policy
        self.max_retries = max_retries
        self.max_steps = max_steps

    def run(
        self,
        task: Task,
        *,
        thought: str = "",
        verify: Optional[Verifier] = None,
    ) -> PlanResult:
        history: list[StepResult] = []
        steps = 0

        while self.orch.step is not Step.DONE and steps < self.max_steps:
            accepts = self.orch.sm.accepts()
            if not accepts:
                break
            kind = sorted(accepts)[0]
            tool_schema = _SCHEMAS[_KIND_TO_TOOL[kind]]

            feedback = None
            result: Optional[StepResult] = None
            for _ in range(self.max_retries + 1):
                raw = self.policy.propose(
                    kind=kind,
                    task=task,
                    step=self.orch.step,
                    tool_schema=tool_schema,
                    kb=self.orch.sm.kb,
                    feedback=feedback,
                )
                result = self.orch.commit_step(
                    kind, raw, task=task, thought=thought, verify=verify
                )
                history.append(result)
                steps += 1
                if result.ok:
                    break
                # carry the rejection back so the policy can self-correct
                feedback = result.violations or (
                    [] if result.verification is None else []
                )

            if result is None or not result.ok:
                return PlanResult(
                    ok=False,
                    final_step=self.orch.step,
                    steps_taken=steps,
                    history=history,
                    aborted_reason=(
                        f"step {kind} failed after {self.max_retries + 1} attempts"
                    ),
                )

        ok = self.orch.step is Step.DONE
        return PlanResult(
            ok=ok,
            final_step=self.orch.step,
            steps_taken=steps,
            history=history,
            aborted_reason=None if ok else "max_steps reached before DONE",
        )
