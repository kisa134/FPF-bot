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
| `memory/graph.py` | Structural memory: SQLite nodes/edges + trajectory log; rejects illegal relations | A.1.1, A.2.4, C.11 |
| `memory/markdown_store.py` | Epistemic memory: lossless FPF-object ↔ Git-friendly Markdown | — |
| `memory/store.py` | Three-layer facade + Git checkpoint/reset + semantic seam | — |

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

## Memory: relational graph over vectors

Classic vector RAG is blind to **hierarchy, causality, and timeline** — the
three things an FPF agent needs. `v1/memory/` replaces it with a three-layer
store, all stdlib (no vector DB required):

1. **Epistemic** — Git-versioned Markdown working set (`markdown_store.py`).
2. **Structural** — SQLite relational graph: `nodes` + `edges`
   (`IN_CONTEXT`, `SUPPORTS`, `RELIES_ON`) + a `trajectory` log
   ("agent X, in context Y, created claim Z"). The graph **rejects illegal
   relations** — e.g. `Evidence -SUPPORTS-> BoundedContext` — a second
   ontology firewall behind the validator.
3. **Semantic** — `LexicalSemanticIndex` (`semantic.py`): stdlib token-overlap
   recall with idf weighting, implementing the `SemanticIndex` protocol. Wired
   optionally into `MemoryStore`; recall is enrichment, never truth. A
   `sqlite-vss`/embedding impl of the same two-method protocol swaps in
   unchanged — the lexical index is the zero-dependency floor.

**Amnesia protection:** the memory root is a Git repo. `checkpoint()` commits a
sane reasoning state; `reset_to(sha)` hard-resets the agent back to it after a
hallucinatory dead end.

## Atomic Cognitive Step (`core/orchestrator.py`)

`StateManager` and `MemoryStore` are fused: the agent cannot change reasoning
state except *through* memory. `Orchestrator.commit_step()` is an all-or-nothing
transaction:

1. **Pre-flight** — wrong step / invalid object → rejected, memory untouched.
2. **Mutate** — markdown + graph (nodes/edges/trajectory) + artifact, then
   `git commit`.
3. **Verify** — sandbox runs the artifact. On `reward == 0` (FAIL/ABSTAIN) the
   step is **rolled back whole**: `forget()` undoes the SQLite rows and
   `git reset --hard` wipes the hallucinated files. The state machine never
   advanced. On PASS the move is admitted and the checkpoint becomes the new
   "last sane state".

`test_atomic_loop.py` proves both paths: a successful step leaves a commit +
DB rows + an advanced state; a failed step returns the filesystem **and** SQLite
to exactly their pre-step state.

## Policy layer (`policy/`)

The first place a reasoning *policy* (a model) enters the protected loop. The
orchestrator owns safety; the policy supplies intent.

- `Policy` protocol — `propose(kind, task, step, tool_schema, kb, feedback)` →
  the raw FPF object for the current step.
- `ScriptedPolicy` — deterministic, for tests (no network).
- `AnthropicPolicy` — Claude emits the step's FPF object via **forced tool
  use** (`tool_choice`), so the model can only act by filling a validated tool
  signature. Lazy `anthropic` import — the core never hard-depends on the SDK.
- `Planner.run(task)` — sequences the policy through `commit_step`, feeds
  rejection violations back for bounded self-correction, aborts cleanly instead
  of looping. `test_planner.py` proves happy path → DONE, self-correction after
  a dangling reference, and clean abort.

## Next

- An embedding/`sqlite-vss` `SemanticIndex` behind the existing seam, when
  lexical recall is no longer enough.
- Wire `Planner` to consult `semantic.recall()` before proposing, so prior
  reasoning informs the next move.
