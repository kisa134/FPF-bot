"""Planner: drives the branching atomic loop with a Policy.

The planner asks the policy for the next move (an FPF object, or finish), runs
object moves through the orchestrator's atomic ``commit_step`` and finish moves
through ``finish``, and feeds rejections back to the policy for bounded
self-correction. Before each move it consults the semantic index so prior
reasoning informs the choice — memory now influences the next step.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from ..core.orchestrator import Orchestrator, StepResult, Task, Verifier
from ..core.state_manager import Step
from ..memory.store import SemanticIndex
from .policy import FINISH, Policy


@dataclass
class PlanResult:
    ok: bool
    final_step: Step
    steps_taken: int
    history: list[StepResult] = field(default_factory=list)
    aborted_reason: Optional[str] = None


class Planner:
    """Sequences a Policy through the branching FPF loop."""

    def __init__(
        self,
        memory_root: str | Path,
        policy: Policy,
        *,
        agent: str = "planner",
        semantic: Optional[SemanticIndex] = None,
        max_retries: int = 2,
        max_steps: int = 24,
    ) -> None:
        self.orch = Orchestrator(memory_root, agent=agent, semantic=semantic)
        self.policy = policy
        self.max_retries = max_retries
        self.max_steps = max_steps

    def run(
        self,
        task: Task,
        *,
        thought: str = "",
        verify: Optional[Verifier] = None,
        on_step: Optional[Callable[[StepResult], None]] = None,
    ) -> PlanResult:
        """Drive the loop. ``on_step`` is called after every move (for live UIs)."""
        history: list[StepResult] = []
        steps = 0

        while self.orch.step is not Step.DONE and steps < self.max_steps:
            recall = self._recall(task)
            feedback = None
            result: Optional[StepResult] = None

            for _ in range(self.max_retries + 1):
                kind, raw = self.policy.choose(
                    task=task,
                    step=self.orch.step,
                    allowed_kinds=self.orch.sm.accepts(),
                    can_finish=self.orch.sm.can_finish(),
                    kb=self.orch.sm.kb,
                    recall=recall,
                    feedback=feedback,
                )
                if kind == FINISH:
                    result = self.orch.finish(task=task)
                else:
                    result = self.orch.commit_step(
                        kind, raw or {}, task=task, thought=thought, verify=verify
                    )
                history.append(result)
                steps += 1
                if on_step is not None:
                    on_step(result)
                if result.ok:
                    break
                feedback = result.violations or []

            if result is None or not result.ok:
                return PlanResult(
                    ok=False,
                    final_step=self.orch.step,
                    steps_taken=steps,
                    history=history,
                    aborted_reason=f"move failed after {self.max_retries + 1} attempts",
                )

        ok = self.orch.step is Step.DONE
        return PlanResult(
            ok=ok,
            final_step=self.orch.step,
            steps_taken=steps,
            history=history,
            aborted_reason=None if ok else "max_steps reached before finishing",
        )

    def _recall(self, task: Task) -> list[str]:
        sem = self.orch.memory.semantic
        if sem is None:
            return []
        return sem.recall(f"{task.id} {task.description}", k=5)
