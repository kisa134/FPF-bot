"""FPF-Swarm — a team of role-specialized agents working a problem together.

Instead of one model proposing moves, a small team debates each move before it
is committed:

  • Architect (generator) proposes the next FPF object + its rationale.
  • Censor (auditor, with veto) independently reviews it against FPF discipline
    — is the claim measurable? does evidence declare scope and recency? does the
    decision compare real options under a rule? — and either approves or vetoes
    with a critique that the Architect must address.
  • Orchestrator (recorder) commits an approved move to shared memory; the
    mechanical validator is the final structural gate.

Every agent action is emitted as an :class:`AgentEvent`, so a UI can show the
whole collaboration live and let you open any agent to see what it is doing.

Using a *different model* for the Censor than the Architect lowers correlated
blind spots — that is the point of the veto, not theatre.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional, Protocol

from ..core.orchestrator import Orchestrator, Task
from ..core.state_manager import Step
from ..core.validator import Violation
from .policy import FINISH, Policy


@dataclass
class AgentEvent:
    agent: str                      # "Architect" | "Censor" | "Orchestrator"
    role: str                       # "generator" | "auditor" | "recorder"
    action: str                     # propose|revise|veto|approve|commit|reject|escalate|done
    content: str                    # human-readable message / thought
    kind: Optional[str] = None
    object_id: Optional[str] = None
    to: Optional[str] = None        # target agent, if a message
    ok: Optional[bool] = None
    round: int = 0


EventSink = Callable[[AgentEvent], None]


class Censor(Protocol):
    """Reviews a proposed move; returns (approve, critique)."""

    def review(
        self, *, kind: str, raw: dict[str, Any], rationale: Optional[str], kb: Any
    ) -> tuple[bool, str]:
        ...


# --------------------------------------------------------------------------- #
# The team runner
# --------------------------------------------------------------------------- #
class SwarmRunner:
    """Drives Architect ↔ Censor debate, commits approved moves to memory."""

    def __init__(
        self,
        memory_root: str | Path,
        architect: Policy,
        censor: Censor,
        *,
        semantic: Any = None,
        max_rounds: int = 2,
        max_steps: int = 40,
    ) -> None:
        self.orch = Orchestrator(memory_root, agent="swarm", semantic=semantic)
        self.architect = architect
        self.censor = censor
        self.max_rounds = max_rounds
        self.max_steps = max_steps

    def run(self, task: Task, on_event: EventSink) -> dict[str, Any]:
        steps = 0
        committed = 0
        stalls = 0

        def _finish_or_stall(reason: str) -> Optional[dict[str, Any]]:
            """If a decision exists, finish; else count a stall (abort if stuck)."""
            nonlocal stalls
            if self.orch.sm.can_finish():
                self.orch.finish(task=task)
                on_event(AgentEvent("Orchestrator", "recorder", "commit",
                                    "Enough is settled — closing the work.",
                                    kind="finish", ok=True))
                return None  # loop will see DONE and exit
            stalls += 1
            if stalls > 4:
                return {"ok": False, "committed": committed, "steps": steps,
                        "reason": reason, "final_phase": self.orch.step.value}
            return False  # skip, keep going

        while self.orch.step is not Step.DONE and steps < self.max_steps:
            steps += 1
            allowed = self.orch.sm.accepts()
            can_finish = self.orch.sm.can_finish()

            kind, raw = self.architect.choose(
                task=task, step=self.orch.step, allowed_kinds=allowed,
                can_finish=can_finish, kb=self.orch.sm.kb,
                recall=self._recall(task), feedback=None,
            )
            rationale = getattr(self.architect, "last_rationale", None)

            if kind == FINISH:
                on_event(AgentEvent("Architect", "generator", "propose",
                                    "Proposes to close the work — the analysis is complete.",
                                    kind="finish", to="Censor"))
                self.orch.finish(task=task)
                on_event(AgentEvent("Orchestrator", "recorder", "commit",
                                    "Work closed.", kind="finish", ok=True))
                break

            on_event(AgentEvent("Architect", "generator", "propose",
                                rationale or f"Proposes {kind}.",
                                kind=kind, object_id=raw.get("id"), to="Censor"))

            # -- debate ---------------------------------------------------- #
            approved, critique = self._debate(kind, raw, rationale, on_event)
            for _round in range(self.max_rounds):
                if approved:
                    break
                # Architect revises in response to the critique.
                kind, raw = self.architect.choose(
                    task=task, step=self.orch.step, allowed_kinds=allowed,
                    can_finish=can_finish, kb=self.orch.sm.kb,
                    recall=self._recall(task),
                    feedback=[Violation("CENSOR_VETO", kind, str(raw.get("id", "?")),
                                        critique, "FPF-review")],
                )
                rationale = getattr(self.architect, "last_rationale", None)
                on_event(AgentEvent("Architect", "generator", "revise",
                                    rationale or "Revises after the critique.",
                                    kind=kind, object_id=raw.get("id"), to="Censor",
                                    round=_round + 1))
                approved, critique = self._debate(kind, raw, rationale, on_event,
                                                  rnd=_round + 1)

            if not approved:
                on_event(AgentEvent("Censor", "auditor", "escalate",
                                    "Could not approve this move after debate.",
                                    kind=kind, object_id=raw.get("id"), ok=False))
                out = _finish_or_stall("escalated: censor veto unresolved")
                if out:
                    return out
                continue

            # -- commit (mechanical validator is the final gate) ----------- #
            res = self.orch.commit_step(kind, raw, task=task, rationale=rationale)
            if res.ok:
                committed += 1
                stalls = 0
                on_event(AgentEvent("Orchestrator", "recorder", "commit",
                                    f"Recorded into shared memory.",
                                    kind=kind, object_id=res.object_id, ok=True))
            else:
                why = res.violations[0].detail if res.violations else "structural check failed"
                on_event(AgentEvent("Orchestrator", "recorder", "reject",
                                    f"Structural firewall rejected: {why}",
                                    kind=kind, object_id=raw.get("id"), ok=False))
                out = _finish_or_stall("stalled: no valid move")
                if out:
                    return out

        ok = self.orch.step is Step.DONE
        on_event(AgentEvent("Orchestrator", "recorder", "done",
                            "Session complete." if ok else "Stopped before completion.",
                            ok=ok))
        return {"ok": ok, "committed": committed, "steps": steps,
                "reason": None if ok else "max steps reached",
                "final_phase": self.orch.step.value}

    def _debate(self, kind, raw, rationale, on_event, rnd=0):
        approve, critique = self.censor.review(
            kind=kind, raw=raw, rationale=rationale, kb=self.orch.sm.kb)
        if approve:
            on_event(AgentEvent("Censor", "auditor", "approve",
                                critique or "Passes FPF review.",
                                kind=kind, object_id=raw.get("id"), to="Orchestrator",
                                ok=True, round=rnd))
        else:
            on_event(AgentEvent("Censor", "auditor", "veto",
                                critique, kind=kind, object_id=raw.get("id"),
                                to="Architect", ok=False, round=rnd))
        return approve, critique

    def _recall(self, task: Task) -> list[str]:
        sem = self.orch.memory.semantic
        return sem.recall(f"{task.id} {task.description}", k=5) if sem else []


# --------------------------------------------------------------------------- #
# Live Censor — a (different) model acting as the skeptic auditor
# --------------------------------------------------------------------------- #
_CENSOR_SYSTEM = (
    "You are the Censor in an FPF reasoning team: a rigorous, skeptical auditor "
    "with the power to VETO. Review the Architect's proposed FPF object against "
    "First-Principles discipline:\n"
    "  • Claim — is it specific and falsifiable (a number, a threshold), not a vibe?\n"
    "  • Evidence — does it declare an explicit scope and a recency window, and is "
    "it honestly empirical vs deductive?\n"
    "  • Decision — does it compare real, distinct options under an explicit rule, "
    "and rely on established claims?\n"
    "  • Anything that is vague, unsupported, or contradicts what is already in the "
    "knowledge base must be vetoed.\n"
    "Be strict but fair. Approve only what would survive expert scrutiny. Reply by "
    "calling the verdict tool with approve=true/false and a sharp one-sentence critique."
)


class LLMCensor:
    """An OpenAI-compatible model acting as the auditing Censor (with veto)."""

    def __init__(self, *, model: str, base_url: str, api_key: str, client: Any = None) -> None:
        if client is None:
            from openai import OpenAI

            client = OpenAI(base_url=base_url, api_key=api_key)
        self._client = client
        self._model = model

    def review(self, *, kind, raw, rationale, kb) -> tuple[bool, str]:
        from .policy import kb_summary

        user = (
            f"Knowledge base so far: {kb_summary(kb)}\n"
            f"Proposed {kind}: {json.dumps(raw, ensure_ascii=False)}\n"
            f"Architect's rationale: {rationale or '(none)'}"
        )
        tool = {
            "type": "function",
            "function": {
                "name": "verdict",
                "description": "Approve or veto the proposed FPF object.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "approve": {"type": "boolean"},
                        "critique": {"type": "string",
                                     "description": "one sharp sentence: why approve or why veto"},
                    },
                    "required": ["approve", "critique"],
                },
            },
        }
        try:
            resp = self._client.chat.completions.create(
                model=self._model, tools=[tool], tool_choice="required",
                messages=[{"role": "system", "content": _CENSOR_SYSTEM},
                          {"role": "user", "content": user}],
            )
            args = resp.choices[0].message.tool_calls[0].function.arguments
            data = json.loads(args) if isinstance(args, str) else dict(args)
            return bool(data.get("approve", True)), str(data.get("critique", ""))
        except Exception as exc:  # if the auditor is unreachable, don't block — note it
            return True, f"(censor unavailable, passed by default: {exc})"
