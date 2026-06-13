"""Atomic Cognitive Step -- the binding of reasoning state to memory.

This module fuses ``StateManager`` (what the agent is allowed to do next) and
``MemoryStore`` (where validated thought is durably recorded) into a single
transactional primitive: :meth:`Orchestrator.commit_step`.

The contract: the agent cannot change its reasoning state except *through*
memory. A step either lands completely (markdown written, graph updated,
trajectory logged, git committed, state machine advanced) or it does not happen
at all (SQLite rolled back, ``git reset --hard`` to the last sane checkpoint,
state machine unmoved).

Two failure gates:
  * ontology firewall (pre-flight, no mutation) -- wrong step / invalid object
  * sandbox verification (post-mutation) -- reward == 0 triggers full rollback
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from ..memory.graph import OntologyError
from ..memory.store import MemoryStore
from .sandbox import SandboxResult, SandboxStatus
from .state_manager import StateManager, Step
from .validator import Violation

# A verifier runs the step's artifact through external checks and returns a
# SandboxResult. ``None`` artifact means "nothing to run".
Verifier = Callable[[Optional[str]], SandboxResult]


@dataclass(frozen=True)
class Task:
    """A unit of work the agent is acting on (the "Work Packet")."""

    id: str
    description: str = ""


@dataclass(frozen=True)
class StepResult:
    """Outcome of one atomic cognitive step."""

    ok: bool
    step_before: Step
    step_after: Step
    object_id: Optional[str]
    sha: Optional[str]  # commit sha when ok
    violations: list[Violation] = field(default_factory=list)
    verification: Optional[SandboxResult] = None
    rolled_back: bool = False


class Orchestrator:
    """Drives the FPF loop with memory as a hard dependency.

    ``commit_step`` is the only way to advance. There is deliberately no public
    method to mutate the state machine or the memory independently.
    """

    def __init__(
        self,
        memory_root: str | Path,
        *,
        agent: str = "agent",
        semantic: Any = None,
    ) -> None:
        self.agent = agent
        self.memory = MemoryStore(memory_root, semantic=semantic)
        self.sm = StateManager()
        # Establish the first "sane" checkpoint so rollback always has a target.
        self.memory.init_repo()
        self._last_good_sha = self.memory.checkpoint("init: empty memory")

    @property
    def step(self) -> Step:
        return self.sm.step

    @property
    def last_good_sha(self) -> str:
        return self._last_good_sha

    # ----------------------------------------------------------------- #
    def commit_step(
        self,
        kind: str,
        raw: dict,
        *,
        task: Task,
        thought: str = "",
        artifact: Optional[str] = None,
        verify: Optional[Verifier] = None,
    ) -> StepResult:
        """Execute one step as an all-or-nothing transaction."""
        before = self.sm.step

        # -- PHASE 1: pre-flight legality + ontology firewall (no mutation) --
        if self.sm.step is Step.DONE:
            return self._reject(
                before, kind, raw, "LOOP_DONE", "reasoning loop already complete"
            )
        if kind not in self.sm.accepts():
            return self._reject(
                before,
                kind,
                raw,
                "WRONG_STEP",
                f"step {before.value} accepts {sorted(self.sm.accepts())}, not {kind!r}",
            )
        from .validator import validate  # local import avoids cycle at import time

        result = validate(kind, raw, self.sm.kb)
        if not result.ok:
            return StepResult(
                ok=False,
                step_before=before,
                step_after=before,
                object_id=str(raw.get("id", "?")),
                sha=None,
                violations=result.violations,
            )
        obj = result.parsed

        # -- PHASE 2: mutate memory (provisional) ---------------------------- #
        prev_sha = self._last_good_sha
        try:
            self.memory.remember(obj, agent=self.agent)
        except OntologyError as exc:  # graph-layer firewall (defense in depth)
            self.memory.reset_to(prev_sha)  # discard any partial markdown write
            return self._reject(before, kind, raw, "GRAPH_FIREWALL", str(exc))

        if artifact is not None or thought:
            self._write_sidecars(obj.id, thought, artifact)
        step_sha = self.memory.checkpoint(
            f"step[{task.id}] {kind}:{obj.id} {task.description}".strip()
        )

        # -- PHASE 3: sandbox verification ----------------------------------- #
        artifact_path = str(self._artifact_path(obj.id)) if artifact is not None else None
        vres = (
            verify(artifact_path)
            if verify is not None
            else SandboxResult(SandboxStatus.PASS, "no verifier registered")
        )

        if vres.status is not SandboxStatus.PASS:  # reward == 0 -> roll back
            self._rollback(obj.id, prev_sha)
            return StepResult(
                ok=False,
                step_before=before,
                step_after=before,  # state machine did not move
                object_id=obj.id,
                sha=None,
                verification=vres,
                rolled_back=True,
            )

        # -- COMMIT: advance the state machine officially -------------------- #
        out = self.sm.submit(kind, raw)
        if not out.accepted:  # pragma: no cover - pre-validated, should not happen
            self._rollback(obj.id, prev_sha)
            return StepResult(
                ok=False,
                step_before=before,
                step_after=before,
                object_id=obj.id,
                sha=None,
                violations=out.violations,
                verification=vres,
                rolled_back=True,
            )
        self._last_good_sha = step_sha
        return StepResult(
            ok=True,
            step_before=before,
            step_after=self.sm.step,
            object_id=obj.id,
            sha=step_sha,
            verification=vres,
        )

    def finish(self, *, task: Task) -> StepResult:
        """Close the WORK phase and move to DONE, checkpointing the result."""
        before = self.sm.step
        out = self.sm.finish()
        if not out.accepted:
            return StepResult(
                ok=False,
                step_before=before,
                step_after=before,
                object_id=None,
                sha=None,
                violations=out.violations,
            )
        sha = self.memory.checkpoint(
            f"finish[{task.id}] {task.description}".strip(), allow_empty=True
        )
        self._last_good_sha = sha
        return StepResult(
            ok=True,
            step_before=before,
            step_after=self.sm.step,
            object_id=None,
            sha=sha,
        )

    # ----------------------------------------------------------------- #
    def _rollback(self, object_id: str, prev_sha: str) -> None:
        """Undo a committed-but-unverified step, leaving no trace.

        Structural undo (SQLite) is explicit because graph.db is not versioned;
        the filesystem undo (markdown + artifacts) is the git reset.
        """
        self.memory.forget(object_id)  # delete node, edges, trajectory rows
        self.memory.reset_to(prev_sha)  # physically remove hallucinated files

    def _reject(
        self, before: Step, kind: str, raw: dict, code: str, detail: str
    ) -> StepResult:
        return StepResult(
            ok=False,
            step_before=before,
            step_after=before,
            object_id=str(raw.get("id", "?")),
            sha=None,
            violations=[
                Violation(
                    code=code,
                    object_kind=kind,
                    object_id=str(raw.get("id", "?")),
                    detail=detail,
                    spec_anchor="orchestrator",
                )
            ],
        )

    def _artifact_dir(self) -> Path:
        d = self.memory.root / "artifacts"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _artifact_path(self, object_id: str) -> Path:
        return self._artifact_dir() / f"{object_id.replace('/', '_')}.artifact"

    def _write_sidecars(
        self, object_id: str, thought: str, artifact: Optional[str]
    ) -> None:
        if artifact is not None:
            self._artifact_path(object_id).write_text(artifact, encoding="utf-8")
        if thought:
            safe = object_id.replace("/", "_")
            (self._artifact_dir() / f"{safe}.thought.md").write_text(
                f"# Reasoning trace for {object_id}\n\n{thought}\n", encoding="utf-8"
            )
