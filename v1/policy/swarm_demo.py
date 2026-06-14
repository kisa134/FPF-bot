"""Offline demo of the FPF-Swarm — a visible Architect ↔ Censor debate.

One object implements both the Architect (proposes) and the Censor (reviews),
driven by a script with deliberately *contested* moves: the Architect first
proposes something weak, the Censor vetoes it with a real FPF critique, and the
Architect revises. This shows the team collaborating live without any network.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

from .policy import FINISH, Move

_NOW = datetime(2026, 6, 14)
_WIN = (_NOW + timedelta(days=90)).isoformat()
_N = _NOW.isoformat()
CTX = "BTC.Telemetry"

# Each turn: dict with kind, fixed (good raw), rationale; optionally a `contested`
# block {flawed, flawed_rationale, critique} that triggers a veto + revision.
_TURNS: list[dict[str, Any]] = [
    {
        "kind": "BoundedContext",
        "fixed": {"id": CTX, "invariants": ["timestamps are UTC and monotonic per source",
                                            "a price tick is immutable once written"]},
        "rationale": "Frame the problem: a Bitcoin telemetry pipeline with its own local invariants.",
        "approval": "Boundary and invariants are explicit — good frame.",
    },
    {
        "kind": "Claim",
        "contested": {
            "flawed": {"id": "c_write", "statement": "Ingest is fast.", "context_id": CTX},
            "flawed_rationale": "Claim that the system ingests quickly.",
            "critique": "‘Fast’ is not falsifiable — state a measurable rate (ticks/sec) or I veto.",
        },
        "fixed": {"id": "c_write", "statement": "Ingest is write-heavy: ~200k ticks/sec at peak.", "context_id": CTX},
        "rationale": "Make the load claim measurable: ~200k ticks/sec at peak.",
        "approval": "Now it is a measurable, testable claim.",
    },
    {
        "kind": "Claim",
        "fixed": {"id": "c_query", "statement": "Reads are time-range aggregations (OHLCV), not point lookups.", "context_id": CTX},
        "rationale": "State the query shape — range scans favor a columnar engine.",
        "approval": "Distinct, decision-relevant claim.",
    },
    {
        "kind": "Evidence",
        "contested": {
            "flawed": {"id": "e_bench", "kind": "empirical", "target_claim_id": "c_write",
                       "claim_scope": "some benchmark", "valid_from": _N, "source": "bench"},
            "flawed_rationale": "Attach a benchmark to the write claim.",
            "critique": "Scope is vague and the window is open-ended — name the dataset and a recency limit.",
        },
        "fixed": {"id": "e_bench", "kind": "empirical", "target_claim_id": "c_write",
                  "claim_scope": "ingest load-test, 3-node cluster, synthetic venue feed, 2026-Q2",
                  "valid_from": _N, "valid_until": _WIN, "source": "loadtest-btc-ingest-07"},
        "rationale": "Give the evidence an explicit scope and a recency window so it can age out.",
        "approval": "Scoped, dated, honestly empirical — accepted.",
    },
    {
        "kind": "DecisionRecord",
        "fixed": {"id": "D1", "context_id": CTX, "decision_subject": "primary datastore for tick telemetry",
                  "option_set": ["TimescaleDB", "Cassandra", "ClickHouse"],
                  "choice_rule": "highest sustained ingest AND native columnar range scans under retention budget",
                  "chosen": "ClickHouse", "supporting_claim_ids": ["c_write", "c_query"]},
        "rationale": "Decide among real options under an explicit rule, relying on the established claims.",
        "approval": "Options and rule are explicit and the choice is grounded in the claims.",
    },
]


class DemoSwarm:
    """Implements both Architect (`choose`) and Censor (`review`) from a script."""

    def __init__(self) -> None:
        self._i = 0
        self._revised: set[int] = set()
        self.last_rationale: Optional[str] = None

    # -- Architect -------------------------------------------------------- #
    def choose(self, **_: Any) -> Move:
        if self._i >= len(_TURNS):
            self.last_rationale = None
            return (FINISH, None)
        turn = _TURNS[self._i]
        contested = turn.get("contested")
        if contested and self._i not in self._revised:
            self.last_rationale = contested["flawed_rationale"]
            return (turn["kind"], dict(contested["flawed"]))
        self.last_rationale = turn["rationale"]
        return (turn["kind"], dict(turn["fixed"]))

    # -- Censor ----------------------------------------------------------- #
    def review(self, *, kind, raw, rationale, kb) -> tuple[bool, str]:
        turn = _TURNS[self._i] if self._i < len(_TURNS) else None
        if turn is None:
            return True, "ok"
        contested = turn.get("contested")
        if contested and self._i not in self._revised:
            self._revised.add(self._i)
            return False, contested["critique"]
        approval = turn.get("approval", "Passes FPF review.")
        self._i += 1  # advance after approval
        return True, approval


def demo_swarm() -> DemoSwarm:
    return DemoSwarm()
