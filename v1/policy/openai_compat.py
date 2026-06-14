"""OpenAI-compatible policy — for DeepSeek, Qwen, Kimi, GLM, and gateways.

Most top Chinese models expose an OpenAI-compatible Chat Completions API with
function calling. This policy targets that surface: the model picks the next FPF
move by emitting a forced tool call, exactly like ``AnthropicPolicy`` — never
free text. Provider-neutral: point it at any ``base_url`` with a ``model`` name.

Nothing here hard-depends on a vendor SDK at import time (the ``openai`` package
is imported lazily), and no credentials are read from anywhere but the caller.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from ..core.orchestrator import Task
from ..core.state_manager import Step
from ..core.validator import KnowledgeBase, Violation
from ..tools.mcp_schema import KIND_TO_TOOL, TOOL_TO_KIND, tool_schemas
from .policy import FINISH, Move, _prompt  # reuse the shared prompt builder

_FINISH_TOOL = "finish_reasoning"
_SCHEMAS = {t["name"]: t["input_schema"] for t in tool_schemas()}

SYSTEM = (
    "You are an FPF reasoning engine. Advance the work by choosing exactly one "
    "move: call one tool to emit an FPF object, or call finish_reasoning to close "
    "the work once at least one decision has been recorded. Every field must "
    "satisfy the tool schema and reference only ids that already exist. The tool "
    "call is your only output — never write prose."
)


class OpenAICompatPolicy:
    """Chooses the next FPF move via an OpenAI-compatible chat-completions API."""

    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        api_key: str,
        client: Any = None,
    ) -> None:
        if client is None:
            from openai import OpenAI  # lazy: core never hard-depends on the SDK

            client = OpenAI(base_url=base_url, api_key=api_key)
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
                "type": "function",
                "function": {
                    "name": KIND_TO_TOOL[k],
                    "description": f"Emit an FPF {k}.",
                    "parameters": _SCHEMAS[KIND_TO_TOOL[k]],
                },
            }
            for k in sorted(allowed_kinds)
        ]
        if can_finish:
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": _FINISH_TOOL,
                        "description": "Close the work phase; the task is complete.",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            )
        resp = self._client.chat.completions.create(
            model=self._model,
            tools=tools,
            tool_choice="required",  # force a tool call (not prose)
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": _prompt(task, step, kb, recall, feedback)},
            ],
        )
        call = resp.choices[0].message.tool_calls[0]
        name = call.function.name
        if name == _FINISH_TOOL:
            return (FINISH, None)
        args = call.function.arguments
        raw = json.loads(args) if isinstance(args, str) else dict(args)
        return (TOOL_TO_KIND[name], raw)
