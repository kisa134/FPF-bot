"""Policy: chooses the next FPF move. The seam where the model drives the loop.

With the branching state machine, the policy decides *both* which move to make
(among several legal object kinds) *and* when to finish — that choice is the
model's, not the machine's. The orchestrator still owns all safety.

Each ``choose`` call returns either ``(kind, raw)`` to emit an FPF object, or
``(FINISH, None)`` to close the work phase. ``AnthropicPolicy`` realizes the
choice as forced tool use: every legal move (plus an optional finish tool) is a
tool, and Claude's tool selection *is* the decision — never free text.

Prior reasoning is wired in via ``recall`` (ids surfaced by the semantic index),
so the model can see "we have reasoned about something like this before".
"""

from __future__ import annotations

from typing import Any, Optional, Protocol

from ..core.orchestrator import Task
from ..core.state_manager import Step
from ..core.validator import KnowledgeBase, Violation
from ..tools.mcp_schema import KIND_TO_TOOL, TOOL_TO_KIND, tool_schemas

# Default model — see the claude-api skill (current Opus-tier).
DEFAULT_MODEL = "claude-opus-4-8"

# Sentinel move: close the work phase instead of emitting an object.
FINISH = "__finish__"
_FINISH_TOOL = "finish_reasoning"

# tool name -> input_schema, built once from the ontology types.
_SCHEMAS = {t["name"]: t["input_schema"] for t in tool_schemas()}


def kb_summary(kb: KnowledgeBase) -> dict[str, list[str]]:
    """Compact view of what already exists, so proposals reference real ids."""
    return {
        "contexts": sorted(kb.contexts),
        "claims": sorted(kb.claims),
        "evidence": sorted(kb.evidence),
        "decisions": sorted(kb.decisions),
        "promises": sorted(kb.promises),
        "commitments": sorted(kb.commitments),
        "methods": sorted(kb.methods),
    }


# A move is (kind, raw) for an object, or (FINISH, None) to close.
Move = tuple[str, Optional[dict[str, Any]]]


class Policy(Protocol):
    """Chooses the next move given the legal options."""

    def choose(
        self,
        *,
        task: Task,
        step: Step,
        allowed_kinds: set[str],
        can_finish: bool,
        kb: KnowledgeBase,
        recall: Optional[list[str]] = None,
        feedback: Optional[list[Violation]] = None,
    ) -> Move:
        ...


class ScriptedPolicy:
    """Deterministic policy for tests: replays a fixed sequence of moves.

    ``moves`` is an ordered list; each item is either a kind string (looked up
    in ``responses`` for its raw object) or the ``FINISH`` sentinel.
    """

    def __init__(self, moves: list[str], responses: dict[str, dict[str, Any]]) -> None:
        self._moves = list(moves)
        self._responses = responses
        self._i = 0

    def choose(self, **_: Any) -> Move:
        if self._i >= len(self._moves):
            return (FINISH, None)
        move = self._moves[self._i]
        self._i += 1
        if move == FINISH:
            return (FINISH, None)
        return (move, self._responses[move])


class AnthropicPolicy:
    """Real policy: Claude picks the next move via forced tool use."""

    SYSTEM = (
        "You are an FPF reasoning engine. Advance the work by choosing exactly one "
        "move: call one tool to emit an FPF object, or call finish_reasoning to "
        "close the work once at least one decision has been recorded. Every field "
        "must satisfy the tool schema and reference only ids that already exist. "
        "The tool call is your only output — never write prose."
    )

    def __init__(self, *, model: str = DEFAULT_MODEL, client: Any = None) -> None:
        if client is None:
            import anthropic  # lazy: core never hard-depends on the SDK

            client = anthropic.Anthropic()
        self._client = client
        self._model = model

    def choose(
        self,
        *,
        task: Task,
        step: Step,
        allowed_kinds: set[str],
        can_finish: bool,
        kb: KnowledgeBase,
        recall: Optional[list[str]] = None,
        feedback: Optional[list[Violation]] = None,
    ) -> Move:
        tools = [
            {
                "name": KIND_TO_TOOL[k],
                "description": f"Emit an FPF {k}.",
                "input_schema": _SCHEMAS[KIND_TO_TOOL[k]],
            }
            for k in sorted(allowed_kinds)
        ]
        if can_finish:
            tools.append(
                {
                    "name": _FINISH_TOOL,
                    "description": "Close the work phase; the task is complete.",
                    "input_schema": {"type": "object", "properties": {}},
                }
            )
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=self.SYSTEM,
            tools=tools,
            tool_choice={"type": "any"},
            messages=[{"role": "user", "content": _prompt(task, step, kb, recall, feedback)}],
        )
        for block in resp.content:
            if getattr(block, "type", None) == "tool_use":
                if block.name == _FINISH_TOOL:
                    return (FINISH, None)
                return (TOOL_TO_KIND[block.name], dict(block.input))
        raise RuntimeError("model did not emit a tool call")


def _prompt(
    task: Task,
    step: Step,
    kb: KnowledgeBase,
    recall: Optional[list[str]],
    feedback: Optional[list[Violation]],
) -> str:
    lines = [
        f"Task: {task.id} — {task.description}",
        f"Phase: {step.value}.",
        f"Knowledge base so far: {kb_summary(kb)}",
    ]
    if recall:
        lines.append(f"Related prior reasoning (object ids): {recall}")
    if feedback:
        lines.append(
            "Your previous move was rejected. Fix these violations:\n"
            + "\n".join(f"- {v}" for v in feedback)
        )
    return "\n".join(lines)
