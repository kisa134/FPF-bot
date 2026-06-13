# FPF Orchestrator V1

A deterministic reasoning harness over the **First Principles Framework**
(`FPF-Spec.md`). The orchestrator constrains an AI agent to emit **typed FPF
objects validated against the spec's invariants** instead of free-form text.

> Design rule: thinking is controlled by *syntactic and ontological frames*,
> not by large "be a smart agent" prompts. Validation lives in types and code.

## Why this shape

Classic prompt-engineering produces a "fragile Frankenstein": the model writes
plausible prose and nothing checks it. Here the model's only way to act is to
fill a **strict tool signature**; every move is gated by a validator that
rejects under-specified or referentially-broken structures.

## Modules

| Module | Responsibility | Spec anchor |
|---|---|---|
| `core/ontology.py` | Pydantic kernel types: `BoundedContext`, `Claim`, `Evidence`, `DecisionRecord` | A.1.1, A.2.4, C.11 |
| `core/validator.py` | Gatekeeper: schema (layer 1) + referential integrity (layer 2) → machine-readable `Violation`s | A.1.1, A.2.4, C.11 |
| `core/state_manager.py` | FPF loop `FRAME → CLAIM → EVIDENCE → DECISION → DONE`; advances only on a valid object | — |
| `core/sandbox.py` | Fail-closed isolated checks turning artifacts into empirical evidence (V1 stub) | A.2.4 |
| `tools/mcp_schema.py` | MCP/tool-use schemas generated from the ontology types | — |

## Invariants enforced today

- **A.1.1** — a `Claim`/`DecisionRecord` `context_id` must point to exactly one
  declared `BoundedContext` (no dangling, no global meaning).
- **A.2.4** — `Evidence` MUST declare `target_claim_id`, `claim_scope`, and a
  `timespan`; **empirical** evidence MUST carry a refresh horizon
  (`valid_until`) — no silent staleness.
- **C.11** — a `DecisionRecord` needs ≥2 options and its `chosen` result must be
  a member of the `option_set`.

## Run the contract

```bash
pip install "pydantic>=2,<3"
python -m unittest discover -s v1/tests -p 'test_*.py' -v
```

## Status / next

V1 = in-memory `KnowledgeBase`. Next milestone: a persistent **memory layer**
(Git-versioned Markdown epistemes + SQLite relational graph) so the validated
objects above are stored as nodes/edges and the agent's reasoning trajectory is
checkpointable. See repo-root discussion / upcoming `v1/memory/`.
