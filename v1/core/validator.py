"""FPF output validator -- the structural gatekeeper.

Two layers of checking:

1. *Intra-object* invariants live in ``ontology.py`` (Pydantic). Parsing raw
   model output through those types already rejects under-specified objects
   (e.g. Evidence without a claim-scope, A.2.4).

2. *Inter-object* invariants live here. Single-object schemas cannot see that a
   Claim points at a non-existent BoundedContext, or that Evidence supports a
   Claim that was never asserted. Those are referential-integrity rules of the
   FPF kernel (A.1.1 "context is total, 1..1"; A.2.4 "target claim") and are
   checked against a :class:`KnowledgeBase`.

The validator never "fixes" output and never asks the model to be smarter. It
returns a machine-readable list of :class:`Violation`. The state machine uses
that list to decide whether the agent may advance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from pydantic import ValidationError

from .ontology import (
    BoundedContext,
    Claim,
    Commitment,
    DecisionRecord,
    Evidence,
    Method,
    PromiseContent,
)

# Map an FPF object kind name -> its Pydantic type, for parsing raw output.
_KINDS: dict[str, type] = {
    "BoundedContext": BoundedContext,
    "Claim": Claim,
    "Evidence": Evidence,
    "DecisionRecord": DecisionRecord,
    "PromiseContent": PromiseContent,
    "Commitment": Commitment,
    "Method": Method,
}


@dataclass(frozen=True)
class Violation:
    """A single machine-readable validation failure."""

    code: str  # stable, e.g. "DANGLING_CONTEXT", "SCHEMA"
    object_kind: str  # "Claim", "Evidence", ...
    object_id: str  # id of the offending object ("?" if unparsable)
    detail: str  # human-readable explanation
    spec_anchor: str  # the FPF section the rule comes from

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return f"[{self.code}] {self.object_kind}:{self.object_id} -- {self.detail} ({self.spec_anchor})"


@dataclass
class KnowledgeBase:
    """The set of FPF objects accepted so far in a session.

    Holds only well-formed (already parsed) objects. The validator checks new
    objects for referential integrity against what this base already contains.
    """

    contexts: dict[str, BoundedContext] = field(default_factory=dict)
    claims: dict[str, Claim] = field(default_factory=dict)
    evidence: dict[str, Evidence] = field(default_factory=dict)
    decisions: dict[str, DecisionRecord] = field(default_factory=dict)
    promises: dict[str, PromiseContent] = field(default_factory=dict)
    commitments: dict[str, Commitment] = field(default_factory=dict)
    methods: dict[str, Method] = field(default_factory=dict)


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of validating one raw object."""

    ok: bool
    parsed: Any | None  # the typed object when ok, else None
    violations: list[Violation]


def parse_object(kind: str, raw: dict[str, Any]) -> tuple[Any | None, list[Violation]]:
    """Parse a raw dict into a typed FPF object, capturing schema violations.

    This is layer 1: intra-object invariants enforced by the ontology types.
    """
    cls = _KINDS.get(kind)
    if cls is None:
        return None, [
            Violation(
                code="UNKNOWN_KIND",
                object_kind=kind,
                object_id=str(raw.get("id", "?")),
                detail=f"unknown FPF object kind {kind!r}; expected one of {sorted(_KINDS)}",
                spec_anchor="orchestrator",
            )
        ]
    try:
        return cls(**raw), []
    except ValidationError as exc:
        oid = str(raw.get("id", "?"))
        violations = []
        for err in exc.errors():
            loc = ".".join(str(p) for p in err["loc"]) or "<root>"
            violations.append(
                Violation(
                    code="SCHEMA",
                    object_kind=kind,
                    object_id=oid,
                    detail=f"{loc}: {err['msg']}",
                    # The mandatory-field rules trace to the type's spec anchor.
                    spec_anchor=_anchor_for(kind),
                )
            )
        return None, violations


def _anchor_for(kind: str) -> str:
    return {
        "BoundedContext": "A.1.1",
        "Claim": "A.1.1",
        "Evidence": "A.2.4",
        "DecisionRecord": "C.11",
        "PromiseContent": "A.2.3",
        "Commitment": "A.2.8",
        "Method": "A.3.1",
    }.get(kind, "FPF")


def check_references(obj: Any, kb: KnowledgeBase) -> list[Violation]:
    """Layer 2: inter-object referential invariants of the FPF kernel."""
    violations: list[Violation] = []

    if isinstance(obj, Claim):
        # A.1.1: a claim's context is total and points to exactly one frame.
        if obj.context_id not in kb.contexts:
            violations.append(
                Violation(
                    code="DANGLING_CONTEXT",
                    object_kind="Claim",
                    object_id=obj.id,
                    detail=f"context_id {obj.context_id!r} is not a declared BoundedContext",
                    spec_anchor="A.1.1",
                )
            )

    elif isinstance(obj, Evidence):
        # A.2.4: evidence must support a claim that actually exists.
        if obj.target_claim_id not in kb.claims:
            violations.append(
                Violation(
                    code="DANGLING_CLAIM",
                    object_kind="Evidence",
                    object_id=obj.id,
                    detail=f"target_claim_id {obj.target_claim_id!r} is not a declared Claim",
                    spec_anchor="A.2.4",
                )
            )

    elif isinstance(obj, DecisionRecord):
        if obj.context_id not in kb.contexts:
            violations.append(
                Violation(
                    code="DANGLING_CONTEXT",
                    object_kind="DecisionRecord",
                    object_id=obj.id,
                    detail=f"context_id {obj.context_id!r} is not a declared BoundedContext",
                    spec_anchor="A.1.1",
                )
            )
        for cid in obj.supporting_claim_ids:
            if cid not in kb.claims:
                violations.append(
                    Violation(
                        code="DANGLING_CLAIM",
                        object_kind="DecisionRecord",
                        object_id=obj.id,
                        detail=f"supporting_claim_id {cid!r} is not a declared Claim",
                        spec_anchor="C.11",
                    )
                )

    elif isinstance(obj, (PromiseContent, Method)):
        # A.1.1: both live in exactly one declared frame.
        if obj.context_id not in kb.contexts:
            violations.append(
                Violation(
                    code="DANGLING_CONTEXT",
                    object_kind=type(obj).__name__,
                    object_id=obj.id,
                    detail=f"context_id {obj.context_id!r} is not a declared BoundedContext",
                    spec_anchor="A.1.1",
                )
            )

    elif isinstance(obj, Commitment):
        if obj.context_id not in kb.contexts:
            violations.append(
                Violation(
                    code="DANGLING_CONTEXT",
                    object_kind="Commitment",
                    object_id=obj.id,
                    detail=f"context_id {obj.context_id!r} is not a declared BoundedContext",
                    spec_anchor="A.1.1",
                )
            )
        # A.2.8: a commitment must bind to a promise content that exists.
        if obj.promise_content_id not in kb.promises:
            violations.append(
                Violation(
                    code="DANGLING_PROMISE",
                    object_kind="Commitment",
                    object_id=obj.id,
                    detail=(
                        f"promise_content_id {obj.promise_content_id!r} is not a "
                        "declared PromiseContent"
                    ),
                    spec_anchor="A.2.8",
                )
            )

    return violations


def validate(kind: str, raw: dict[str, Any], kb: KnowledgeBase) -> ValidationResult:
    """Validate one raw object end-to-end against the knowledge base.

    Schema (layer 1) first; only if it parses do we check references (layer 2).
    On success the object is *not* auto-committed -- the caller decides whether
    to admit it via :func:`admit`.
    """
    parsed, schema_violations = parse_object(kind, raw)
    if parsed is None:
        return ValidationResult(ok=False, parsed=None, violations=schema_violations)

    ref_violations = check_references(parsed, kb)
    if ref_violations:
        return ValidationResult(ok=False, parsed=None, violations=ref_violations)

    return ValidationResult(ok=True, parsed=parsed, violations=[])


def admit(obj: Any, kb: KnowledgeBase) -> None:
    """Record a validated object into the knowledge base."""
    if isinstance(obj, BoundedContext):
        kb.contexts[obj.id] = obj
    elif isinstance(obj, Claim):
        kb.claims[obj.id] = obj
    elif isinstance(obj, Evidence):
        kb.evidence[obj.id] = obj
    elif isinstance(obj, DecisionRecord):
        kb.decisions[obj.id] = obj
    elif isinstance(obj, PromiseContent):
        kb.promises[obj.id] = obj
    elif isinstance(obj, Commitment):
        kb.commitments[obj.id] = obj
    elif isinstance(obj, Method):
        kb.methods[obj.id] = obj
    else:  # pragma: no cover - defensive
        raise TypeError(f"cannot admit object of type {type(obj).__name__}")


def validate_batch(
    items: Iterable[tuple[str, dict[str, Any]]], kb: KnowledgeBase
) -> list[Violation]:
    """Validate and admit a sequence of (kind, raw) items in order.

    Order matters: a Claim must be admitted before Evidence can reference it.
    Returns all violations encountered; admitted objects mutate ``kb`` in place.
    """
    all_violations: list[Violation] = []
    for kind, raw in items:
        result = validate(kind, raw, kb)
        if result.ok:
            admit(result.parsed, kb)
        else:
            all_violations.extend(result.violations)
    return all_violations
