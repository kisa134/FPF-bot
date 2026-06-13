"""Tool (MCP-style) interfaces for the FPF orchestrator.

FPF itself does not define MCP (there is no mention of it in FPF-Spec.md); this
layer is the orchestrator's own contribution. The point of exposing the FPF
moves as *typed tools* -- rather than one giant "be a smart agent" prompt -- is
that the model's only way to act is to fill a strict, validated signature. The
schemas below are the JSON-Schema views of the ontology types, suitable for an
MCP/tool-use ``tools=[...]`` declaration.

Generated straight from the Pydantic models so the tool contract can never
drift from the validated structure.
"""

from __future__ import annotations

from typing import Any

from ..core.ontology import (
    BoundedContext,
    Claim,
    Commitment,
    DecisionRecord,
    Evidence,
    Method,
    PromiseContent,
)

# One tool per FPF move. Names match the state-machine steps' accepted kinds.
_TOOL_MODELS = {
    "declare_bounded_context": (BoundedContext, "Declare a semantic frame (A.1.1)."),
    "submit_claim": (Claim, "Assert a claim inside a bounded context (A.1.1)."),
    "attach_evidence": (Evidence, "Attach evidence to a target claim (A.2.4)."),
    "record_decision": (DecisionRecord, "Record a local choice (C.11)."),
    "submit_promise_content": (
        PromiseContent,
        "State what is promised, separate from who commits (A.2.3).",
    ),
    "submit_commitment": (
        Commitment,
        "Bind a party to a promise content (A.2.8).",
    ),
    "submit_method": (Method, "Define a context-local way of doing (A.3.1)."),
}


def tool_schemas() -> list[dict[str, Any]]:
    """Return MCP/tool-use tool definitions derived from the ontology types."""
    tools: list[dict[str, Any]] = []
    for name, (model, desc) in _TOOL_MODELS.items():
        tools.append(
            {
                "name": name,
                "description": desc,
                "input_schema": model.model_json_schema(),
            }
        )
    return tools


# Maps a tool name back to the FPF object kind the validator/state-machine use.
TOOL_TO_KIND = {
    "declare_bounded_context": "BoundedContext",
    "submit_claim": "Claim",
    "attach_evidence": "Evidence",
    "record_decision": "DecisionRecord",
    "submit_promise_content": "PromiseContent",
    "submit_commitment": "Commitment",
    "submit_method": "Method",
}
KIND_TO_TOOL = {v: k for k, v in TOOL_TO_KIND.items()}
