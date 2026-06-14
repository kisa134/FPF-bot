"""FPF kernel ontology as typed data structures.

This module is the *single source of structural truth* for the orchestrator.
Every type here maps to a concrete pattern in ``FPF-Spec.md`` and carries only
the fields that the specification makes mandatory. The goal is NOT to model all
of FPF, but to make the canonical reasoning objects (Claim, Evidence, decision,
semantic frame) impossible to express in an under-specified form.

Spec anchors (section numbers in FPF-Spec.md):
  - U.BoundedContext ........ A.1.1   (context is total, cardinality 1..1)
  - U.EvidenceRole .......... A.2.4   (MUST declare target claim, claim-scope,
                                       timespan of relevance)
  - Decision Theory ......... C.11    (DecisionSubject, OptionSet, ChoiceRule,
                                       ChoiceResult)

Design rule: validation lives in the *types*, not in prose prompts. If a model
emits an object that violates an FPF invariant, construction fails here with a
machine-readable error rather than passing as plausible-looking text.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Frozen(BaseModel):
    """Base for FPF objects: immutable, no silent extra fields.

    ``extra='forbid'`` is the structural firewall: an LLM cannot smuggle
    free-form keys past the schema. ``frozen=True`` keeps reasoning objects
    auditable once recorded.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)


# --------------------------------------------------------------------------- #
# A.1.1 - U.BoundedContext: the semantic frame
# --------------------------------------------------------------------------- #
class BoundedContext(_Frozen):
    """A named semantic frame ("specific room", not "the whole building").

    Per A.1.1, a bounded context is a governable model locale with an explicit
    glossary and local invariants -- not a mere namespace. We require an id and
    at least one declared invariant so a context cannot be an empty label.
    """

    id: str = Field(
        ...,
        min_length=1,
        description="Stable context id, e.g. 'Hospital.OR_2025' or 'BPMN_2_0'.",
    )
    glossary: dict[str, str] = Field(
        default_factory=dict,
        description="Local term -> local meaning. Local vocabulary of the frame.",
    )
    invariants: list[str] = Field(
        ...,
        min_length=1,
        description="Local rules that hold inside this frame (at least one).",
    )


# --------------------------------------------------------------------------- #
# Claim -- the bedrock reasoning object
# --------------------------------------------------------------------------- #
class Claim(_Frozen):
    """A statement asserted *inside one bounded context*.

    FPF keeps meaning local (A.1.1), so a claim is never global: it always
    names the context in which it holds.
    """

    id: str = Field(..., min_length=1, description="Stable claim id.")
    statement: str = Field(
        ..., min_length=1, description="The asserted proposition, in plain text."
    )
    context_id: str = Field(
        ...,
        min_length=1,
        description="Bounded context in which this claim holds (A.1.1, 1..1).",
    )


class EvidenceKind(str, Enum):
    """A.2.4:3 distinguishes deductive support from ageing empirical support."""

    DEDUCTIVE = "deductive"  # proof/derivation: stable relative to a theory
    EMPIRICAL = "empirical"  # dataset/benchmark/replication: ages, needs refresh


class Timespan(_Frozen):
    """Validity window for an evidence-role assignment (A.2.4).

    Empirical evidence decays; without an explicit window stale evidence keeps
    influencing conclusions. ``valid_until`` may be open (None) only for
    deductive support -- enforced in :class:`Evidence`.
    """

    valid_from: datetime
    valid_until: Optional[datetime] = None

    @model_validator(mode="after")
    def _ordered(self) -> "Timespan":
        if self.valid_until is not None and self.valid_until < self.valid_from:
            raise ValueError("timespan.valid_until precedes valid_from")
        return self


# --------------------------------------------------------------------------- #
# A.2.4 - U.EvidenceRole: an episteme serving as evidence for a claim
# --------------------------------------------------------------------------- #
class Evidence(_Frozen):
    """An episteme assigned the evidence role for a *specific* target claim.

    A.2.4 (normative): the evidence-role assignment MUST declare the target
    claim, the claim-scope, and a timespan of relevance. All three are required
    fields here; absence is a construction error, not a soft warning.
    """

    id: str = Field(..., min_length=1, description="Stable evidence id.")
    kind: EvidenceKind
    # The three mandatory declarations from A.2.4:
    target_claim_id: str = Field(
        ..., min_length=1, description="Claim this evidence supports (A.2.4)."
    )
    claim_scope: str = Field(
        ...,
        min_length=1,
        description="Applicability scope of the support (A.2.4). No bare citations.",
    )
    # Flat date strings (LLM-friendly) instead of a nested object — the validity
    # window of relevance (A.2.4), e.g. "2026-Q2" or "2026-06-14".
    valid_from: str = Field(
        ..., min_length=1, description="When the evidence becomes valid (a date/period)."
    )
    valid_until: Optional[str] = Field(
        None,
        description="When the evidence goes stale (a date/period). REQUIRED for "
        "empirical evidence — empirical support ages (A.2.4).",
    )
    source: str = Field(
        ..., min_length=1, description="The episteme acting as evidence (e.g. a ref)."
    )

    @model_validator(mode="after")
    def _empirical_needs_horizon(self) -> "Evidence":
        # A.2.4:3 "static truth versus ageing confidence": empirical support
        # decays and must carry a refresh horizon.
        if self.kind is EvidenceKind.EMPIRICAL and not self.valid_until:
            raise ValueError(
                "empirical evidence requires valid_until "
                "(A.2.4: empirical support ages and needs a refresh horizon)"
            )
        return self


# --------------------------------------------------------------------------- #
# C.11 - Decision Theory: a recorded local choice
# --------------------------------------------------------------------------- #
class DecisionRecord(_Frozen):
    """A lawful local choice among already-available options (C.11).

    C.11 makes a choice well-formed only when the decision subject, the option
    set, the comparison/choice rule, and the chosen result are all explicit.
    The chosen option must be one of the offered options -- enforced below.
    """

    id: str = Field(..., min_length=1, description="Stable decision id.")
    context_id: str = Field(
        ..., min_length=1, description="Frame in which the choice is lawful (A.1.1)."
    )
    decision_subject: str = Field(
        ..., min_length=1, description="C.11 DecisionSubject: what is being decided."
    )
    option_set: list[str] = Field(
        ...,
        min_length=2,
        description="C.11 OptionSet: at least two candidates (no foregone choice).",
    )
    choice_rule: str = Field(
        ..., min_length=1, description="C.11 ChoiceRule: basis for selecting."
    )
    chosen: str = Field(
        ..., min_length=1, description="C.11 ChoiceResult: the selected option."
    )
    supporting_claim_ids: list[str] = Field(
        default_factory=list,
        description="Claims this decision relies on (traceability into Claim/Evidence).",
    )

    @model_validator(mode="after")
    def _chosen_in_options(self) -> "DecisionRecord":
        if self.chosen not in self.option_set:
            raise ValueError(
                "ChoiceResult must be a member of OptionSet (C.11): "
                f"{self.chosen!r} not in {self.option_set!r}"
            )
        return self


# --------------------------------------------------------------------------- #
# A.2.3 - U.PromiseContent: what is promised (separate from who commits)
# --------------------------------------------------------------------------- #
class PromiseContent(_Frozen):
    """The content of a promise — what is promised, not who is bound (A.2.3).

    FPF keeps promise *content* separate from the *commitment* that binds a
    party to it (A.2.8). A PromiseContent is a reusable description of an
    obligation's substance, local to one bounded context.
    """

    id: str = Field(..., min_length=1, description="Stable promise-content id.")
    context_id: str = Field(
        ..., min_length=1, description="Frame the promise content holds in (A.1.1)."
    )
    statement: str = Field(
        ..., min_length=1, description="What is promised, in plain text."
    )
    conditions: list[str] = Field(
        default_factory=list,
        description="Conditions under which the promise content applies.",
    )


class CommitmentState(str, Enum):
    """A.2.8 deontic lifecycle (minimal)."""

    ACTIVE = "active"
    DISCHARGED = "discharged"
    CANCELLED = "cancelled"


# --------------------------------------------------------------------------- #
# A.2.8 - U.Commitment: a party bound to a promise content
# --------------------------------------------------------------------------- #
class Commitment(_Frozen):
    """A deontic commitment: a debtor bound to a creditor for a PromiseContent.

    A.2.8 separates the obligation (this object) from its content (A.2.3) and
    from the speech act that created it (A.2.9). The commitment must name the
    promise content it binds to, and both parties, inside one context.
    """

    id: str = Field(..., min_length=1, description="Stable commitment id.")
    context_id: str = Field(
        ..., min_length=1, description="Frame the commitment holds in (A.1.1)."
    )
    promise_content_id: str = Field(
        ..., min_length=1, description="The PromiseContent this binds to (A.2.3)."
    )
    debtor: str = Field(
        ..., min_length=1, description="The party obligated (A.2.8)."
    )
    creditor: str = Field(
        ..., min_length=1, description="The party the obligation is owed to (A.2.8)."
    )
    state: CommitmentState = Field(default=CommitmentState.ACTIVE)


# --------------------------------------------------------------------------- #
# A.3.1 - U.Method: a context-defined way of doing
# --------------------------------------------------------------------------- #
class Method(_Frozen):
    """A context-defined way of doing work (A.3.1).

    A.3 keeps the method (the way of doing) distinct from its description and
    from performed work. This is the way itself, named and scoped to a context.
    """

    id: str = Field(..., min_length=1, description="Stable method id.")
    context_id: str = Field(
        ..., min_length=1, description="Frame the method is defined in (A.1.1)."
    )
    name: str = Field(..., min_length=1, description="The method's name.")
    description: str = Field(
        ..., min_length=1, description="What the way of doing consists of."
    )
