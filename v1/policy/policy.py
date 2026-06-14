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

# Shared, demanding instruction: think *through* FPF, not the minimum to DONE.
SYSTEM_PROMPT = (
    "You are an FPF reasoning engine. Work a real, thorough analysis of the task "
    "through the First Principles Framework — do not rush to a decision.\n"
    "Build the reasoning step by step by calling one tool per move:\n"
    "  • first declare a BoundedContext (the frame and its local invariants);\n"
    "  • assert SEVERAL distinct Claims that actually bear on the question;\n"
    "  • attach Evidence to the important claims, each with an explicit scope and "
    "recency window; mark empirical vs deductive honestly;\n"
    "  • when you decide, lay out the real option set and the choice rule, and "
    "rely on the claims you established;\n"
    "  • use PromiseContent / Commitment / Method where the task involves "
    "obligations or ways of working.\n"
    "Only call finish_reasoning once the analysis genuinely covers the question "
    "(typically after multiple claims, evidence, and a justified decision).\n"
    "CRITICAL — keep moving forward: NEVER re-declare or duplicate anything whose "
    "id already appears in the knowledge base. Each id is created exactly once. "
    "Declare the context only once, then move on to claims → evidence → a "
    "decision. After a few claims (with evidence) and one justified decision, call "
    "finish_reasoning. Do not stall or repeat yourself.\n"
    "EVERY tool call MUST include a `rationale`: one or two plain sentences saying "
    "WHY you are making this move now. The tool call is your only output."
)


def with_rationale(schema: dict[str, Any]) -> dict[str, Any]:
    """Add a required `rationale` property to a tool's input schema."""
    s = json_copy(schema)
    s.setdefault("properties", {})["rationale"] = {
        "type": "string",
        "description": "One or two plain sentences: why this move, now.",
    }
    return s


def json_copy(obj: Any) -> Any:
    import copy

    return copy.deepcopy(obj)


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

    def __init__(
        self,
        moves: list[str],
        responses: dict[str, dict[str, Any]],
        rationales: Optional[dict[str, str]] = None,
    ) -> None:
        self._moves = list(moves)
        self._responses = responses
        self._rationales = rationales or {}
        self._i = 0
        self.last_rationale: Optional[str] = None

    def choose(self, **_: Any) -> Move:
        if self._i >= len(self._moves):
            return (FINISH, None)
        move = self._moves[self._i]
        self._i += 1
        key = move if move != FINISH else "finish"
        self.last_rationale = self._rationales.get(f"{key}:{self._i}") or self._rationales.get(key)
        if move == FINISH:
            return (FINISH, None)
        return (move, self._responses[move])


class SequencePolicy:
    """Replays an explicit list of moves with rationales (for rich demos/tests).

    Each move is ``(kind, raw, rationale)`` or the ``FINISH`` sentinel.
    """

    def __init__(self, moves: list) -> None:
        self._moves = list(moves)
        self._i = 0
        self.last_rationale: Optional[str] = None

    def choose(self, **_: Any) -> Move:
        if self._i >= len(self._moves):
            self.last_rationale = None
            return (FINISH, None)
        m = self._moves[self._i]
        self._i += 1
        if m == FINISH:
            self.last_rationale = None
            return (FINISH, None)
        kind, raw, rationale = m
        self.last_rationale = rationale
        return (kind, raw)


class AnthropicPolicy:
    """Real policy: Claude picks the next move via forced tool use."""

    SYSTEM = SYSTEM_PROMPT

    def __init__(self, *, model: str = DEFAULT_MODEL, client: Any = None) -> None:
        if client is None:
            import anthropic  # lazy: core never hard-depends on the SDK

            client = anthropic.Anthropic()
        self._client = client
        self._model = model
        self.last_rationale: Optional[str] = None

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
                "input_schema": with_rationale(_SCHEMAS[KIND_TO_TOOL[k]]),
            }
            for k in sorted(allowed_kinds)
        ]
        if can_finish:
            tools.append(
                {
                    "name": _FINISH_TOOL,
                    "description": "Close the work phase; the task is complete.",
                    "input_schema": with_rationale({"type": "object", "properties": {}}),
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
                args = dict(block.input)
                self.last_rationale = args.pop("rationale", None)
                if block.name == _FINISH_TOOL:
                    return (FINISH, None)
                return (TOOL_TO_KIND[block.name], args)
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
