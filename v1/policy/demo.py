"""A rich, offline FPF demo — a full analysis with rationales, no network.

Used by the `demo` provider so even without a model the studio shows what real
FPF reasoning looks like: a frame, several claims, graded evidence, and a
justified decision among alternatives — each move with the reasoning behind it.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from .policy import FINISH, SequencePolicy

_NOW = datetime(2026, 6, 14)
_SOON = (_NOW + timedelta(days=90)).isoformat()
_N = _NOW.isoformat()
CTX = "BTC.Telemetry"


def _ctx(cid):
    return {
        "id": cid,
        "glossary": {"tick": "one price observation", "p99": "99th-percentile latency"},
        "invariants": [
            "timestamps are UTC and monotonic per source",
            "a price tick is immutable once written",
        ],
    }


# A full reasoning trajectory: (kind, raw, rationale) | FINISH
MOVES = [
    (
        "BoundedContext",
        _ctx(CTX),
        "Frame the problem first: a Bitcoin telemetry pipeline has its own local "
        "meanings (tick, retention) and invariants, so everything below is judged "
        "inside this context.",
    ),
    (
        "Claim",
        {"id": "c_write", "statement": "Ingest is write-heavy: ~200k ticks/sec at peak across venues.", "context_id": CTX},
        "Before choosing tech I state the dominant load characteristic — write "
        "throughput — because it drives most of the decision.",
    ),
    (
        "Claim",
        {"id": "c_query", "statement": "Reads are time-range aggregations (OHLCV over windows), not point lookups.", "context_id": CTX},
        "The query shape matters as much as writes: range scans favor a columnar "
        "/ time-series engine over a key-value store.",
    ),
    (
        "Claim",
        {"id": "c_retention", "statement": "Two years of tick history must stay queryable for backtesting.", "context_id": CTX},
        "Retention is a hard requirement for price prediction backtests, so storage "
        "cost and compression are in scope.",
    ),
    (
        "Evidence",
        {
            "id": "e_bench", "kind": "empirical", "target_claim_id": "c_write",
            "claim_scope": "ingest benchmark on 3-node cluster, synthetic venue feed, 2026-Q2",
            "valid_from": _N, "valid_until": _SOON, "source": "loadtest-btc-ingest-07",
        },
        "I attach a dated, scoped benchmark to the write claim so it counts as "
        "empirical evidence — and mark when it goes stale.",
    ),
    (
        "Evidence",
        {
            "id": "e_pattern", "kind": "empirical", "target_claim_id": "c_query",
            "claim_scope": "query-log analysis of the existing analytics workload, last 30 days",
            "valid_from": _N, "valid_until": _SOON, "source": "query-audit-2026-05",
        },
        "The query-shape claim needs evidence too: a real query-log audit shows "
        "range aggregations dominate, justifying a columnar engine.",
    ),
    (
        "DecisionRecord",
        {
            "id": "D1", "context_id": CTX, "decision_subject": "primary datastore for tick telemetry",
            "option_set": ["TimescaleDB", "Cassandra", "ClickHouse"],
            "choice_rule": "highest sustained ingest AND native columnar range scans under the retention/cost budget",
            "chosen": "ClickHouse", "supporting_claim_ids": ["c_write", "c_query", "c_retention"],
        },
        "Now I decide among real alternatives against an explicit rule, relying on "
        "the three established claims: ClickHouse wins on columnar range scans and "
        "compression for long retention.",
    ),
    FINISH,
]


def demo_policy() -> SequencePolicy:
    return SequencePolicy(MOVES)
