"""Policy: decides the next FPF object to emit. The seam for the model call.

The orchestrator guarantees *safety* (validation, rollback); the policy supplies
*intent* — what to propose next. Keeping it behind a protocol means the core
loop is testable with a deterministic ``ScriptedPolicy`` and never depends on a
network call or an API key. ``AnthropicPolicy`` is the real implementation:
Claude is forced to emit the step's FPF object via tool use, so the model can
only act by filling a strict, validated tool signature — never free text.
"""

from __future__ import annotations

from typing import Any, Optional, Protocol

from ..core.orchestrator import Task
from ..core.state_manager import Step
from ..core.validator import KnowledgeBase, Violation

# Default model — see the claude-api skill (current Opus-tier).
DEFAULT_MODEL = "claude-opus-4-8"


def kb_summary(kb: KnowledgeBase) -> dict[str, list[str]]:
    """Compact view of what already exists, so proposals reference real ids."""
    return {
        "contexts": sorted(kb.contexts),
        "claims": sorted(kb.claims),
        "evidence": sorted(kb.evidence),
        "decisions": sorted(kb.decisions),
    }


class Policy(Protocol):
    """Proposes the raw object for the current FPF move."""

    def propose(
        self,
        *,
        kind: str,
        task: Task,
        step: Step,
        tool_schema: dict[str, Any],
        kb: KnowledgeBase,
        feedback: Optional[list[Violation]] = None,
    ) -> dict[str, Any]:
        """Return a raw dict for ``Orchestrator.commit_step(kind, raw, ...)``.

        ``feedback`` carries violations from a rejected previous attempt so an
        intelligent policy can correct itself.
        """
        ...


class ScriptedPolicy:
    """Deterministic policy for tests: returns a pre-supplied object per kind."""

    def __init__(self, responses: dict[str, dict[str, Any]]) -> None:
        self._responses = responses

    def propose(
        self,
        *,
        kind: str,
        task: Task,
        step: Step,
        tool_schema: dict[str, Any],
        kb: KnowledgeBase,
        feedback: Optional[list[Violation]] = None,
    ) -> dict[str, Any]:
        if kind not in self._responses:
            raise KeyError(f"ScriptedPolicy has no response for kind {kind!r}")
        return self._responses[kind]


class AnthropicPolicy:
    """Real policy: Claude emits the FPF object via forced tool use.

    The model never writes free text into the loop — ``tool_choice`` forces the
    single FPF tool for the current step, and the tool's ``input`` (already
    schema-shaped) becomes the raw object handed to ``commit_step``. Validation
    still happens downstream; this only supplies intent.
    """

    SYSTEM = (
        "You are an FPF reasoning engine. Advance the work by emitting exactly one "
        "FPF object for the current step, by calling the provided tool. Every field "
        "must satisfy the tool schema and reference only ids that already exist in "
        "the knowledge base. Do not write prose; the tool call is your only output."
    )

    def __init__(self, *, model: str = DEFAULT_MODEL, client: Any = None) -> None:
        if client is None:
            import anthropic  # lazy: core never hard-depends on the SDK

            client = anthropic.Anthropic()
        self._client = client
        self._model = model

    def propose(
        self,
        *,
        kind: str,
        task: Task,
        step: Step,
        tool_schema: dict[str, Any],
        kb: KnowledgeBase,
        feedback: Optional[list[Violation]] = None,
    ) -> dict[str, Any]:
        tool_name = _tool_name_for(kind)
        user = _build_user_prompt(kind, task, step, kb, feedback)
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=self.SYSTEM,
            tools=[
                {
                    "name": tool_name,
                    "description": f"Emit the FPF {kind} for this step.",
                    "input_schema": tool_schema,
                }
            ],
            tool_choice={"type": "tool", "name": tool_name},
            messages=[{"role": "user", "content": user}],
        )
        for block in resp.content:
            if getattr(block, "type", None) == "tool_use":
                return dict(block.input)
        raise RuntimeError(f"model did not emit a {tool_name} tool call")


def _tool_name_for(kind: str) -> str:
    return {
        "BoundedContext": "declare_bounded_context",
        "Claim": "submit_claim",
        "Evidence": "attach_evidence",
        "DecisionRecord": "record_decision",
    }[kind]


def _build_user_prompt(
    kind: str,
    task: Task,
    step: Step,
    kb: KnowledgeBase,
    feedback: Optional[list[Violation]],
) -> str:
    lines = [
        f"Task: {task.id} — {task.description}",
        f"Current step: {step.value} (emit one {kind}).",
        f"Knowledge base so far: {kb_summary(kb)}",
    ]
    if feedback:
        lines.append(
            "Your previous attempt was rejected. Fix these violations:\n"
            + "\n".join(f"- {v}" for v in feedback)
        )
    return "\n".join(lines)
