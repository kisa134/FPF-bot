"""Relational reasoning graph over stdlib sqlite3 -- the structural memory.

This is the answer to "classic RAG is a dead end for agents". A vector store
retrieves chunks by surface similarity and is blind to the three things an
agent actually needs:

  * hierarchy   -> here: IN_CONTEXT edges (an object belongs to one frame)
  * causality   -> here: SUPPORTS / RELIES_ON edges (why a thing holds)
  * timeline    -> here: created_at on every row + a monotonic trajectory log

The graph is also a second ontology firewall. The validator (``core``) gates
what enters working memory; the graph gates what gets *related*: you cannot
attach an Evidence->SUPPORTS edge to anything that is not a Claim, and you
cannot create an edge to a node that does not exist (enforced by foreign keys).

No third-party dependencies. One file = the whole structural store.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

# The only edge shapes the FPF kernel allows, as (from_kind, rel, to_kind).
# This mirrors the referential invariants in core/validator.py:
#   A.1.1  Claim/DecisionRecord live in exactly one BoundedContext
#   A.2.4  Evidence supports a Claim
#   C.11   a DecisionRecord relies on Claims
_ALLOWED_EDGES: set[tuple[str, str, str]] = {
    ("Claim", "IN_CONTEXT", "BoundedContext"),
    ("DecisionRecord", "IN_CONTEXT", "BoundedContext"),
    ("Evidence", "SUPPORTS", "Claim"),
    ("DecisionRecord", "RELIES_ON", "Claim"),
    ("PromiseContent", "IN_CONTEXT", "BoundedContext"),
    ("Commitment", "IN_CONTEXT", "BoundedContext"),
    ("Commitment", "PROMISES", "PromiseContent"),
    ("Method", "IN_CONTEXT", "BoundedContext"),
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
    id         TEXT PRIMARY KEY,
    kind       TEXT NOT NULL,
    context_id TEXT,                 -- frame the node lives in (NULL for a frame)
    path       TEXT,                 -- markdown file backing this node
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS edges (
    from_id    TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    to_id      TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    rel        TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (from_id, to_id, rel)
);
CREATE TABLE IF NOT EXISTS trajectory (
    seq         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    agent       TEXT NOT NULL,
    context_id  TEXT,
    action      TEXT NOT NULL,       -- create | reject | checkpoint ...
    object_kind TEXT,
    object_id   TEXT,
    status      TEXT NOT NULL,       -- accepted | rejected
    detail      TEXT
);
CREATE INDEX IF NOT EXISTS idx_edges_to ON edges(to_id, rel);
CREATE INDEX IF NOT EXISTS idx_nodes_ctx ON nodes(context_id);
"""


class OntologyError(ValueError):
    """Raised when a write would violate an FPF structural invariant."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Node:
    id: str
    kind: str
    context_id: Optional[str]
    path: Optional[str]
    created_at: str


@dataclass(frozen=True)
class Edge:
    from_id: str
    to_id: str
    rel: str
    created_at: str


@dataclass(frozen=True)
class TrajectoryEntry:
    seq: int
    ts: str
    agent: str
    context_id: Optional[str]
    action: str
    object_kind: Optional[str]
    object_id: Optional[str]
    status: str
    detail: Optional[str]


class ReasoningGraph:
    """SQLite-backed graph of FPF objects and their relations."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON;")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "ReasoningGraph":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- nodes -------------------------------------------------------------- #
    def add_node(
        self,
        node_id: str,
        kind: str,
        context_id: Optional[str] = None,
        path: Optional[str] = None,
    ) -> Node:
        if self.get_node(node_id) is not None:
            raise OntologyError(f"node {node_id!r} already exists")
        created = _now()
        self._conn.execute(
            "INSERT INTO nodes(id, kind, context_id, path, created_at) VALUES (?,?,?,?,?)",
            (node_id, kind, context_id, path, created),
        )
        self._conn.commit()
        return Node(node_id, kind, context_id, path, created)

    def get_node(self, node_id: str) -> Optional[Node]:
        row = self._conn.execute(
            "SELECT * FROM nodes WHERE id = ?", (node_id,)
        ).fetchone()
        return _row_to_node(row) if row else None

    # -- edges -------------------------------------------------------------- #
    def add_edge(self, from_id: str, to_id: str, rel: str) -> Edge:
        """Relate two nodes -- rejecting any shape the FPF kernel forbids."""
        src = self.get_node(from_id)
        dst = self.get_node(to_id)
        if src is None:
            raise OntologyError(f"edge source {from_id!r} is not a node")
        if dst is None:
            raise OntologyError(f"edge target {to_id!r} is not a node")
        shape = (src.kind, rel, dst.kind)
        if shape not in _ALLOWED_EDGES:
            raise OntologyError(
                f"illegal edge {src.kind}-[{rel}]->{dst.kind}; "
                f"allowed: {sorted(_ALLOWED_EDGES)}"
            )
        created = _now()
        self._conn.execute(
            "INSERT OR IGNORE INTO edges(from_id, to_id, rel, created_at) VALUES (?,?,?,?)",
            (from_id, to_id, rel, created),
        )
        self._conn.commit()
        return Edge(from_id, to_id, rel, created)

    def neighbors(
        self, node_id: str, rel: Optional[str] = None, incoming: bool = False
    ) -> list[Node]:
        """Nodes reachable from (or pointing at) ``node_id`` along ``rel``."""
        col, other = ("to_id", "from_id") if incoming else ("from_id", "to_id")
        sql = f"SELECT {other} AS nid FROM edges WHERE {col} = ?"
        params: list[object] = [node_id]
        if rel is not None:
            sql += " AND rel = ?"
            params.append(rel)
        ids = [r["nid"] for r in self._conn.execute(sql, params).fetchall()]
        return [n for nid in ids if (n := self.get_node(nid)) is not None]

    def delete_object(self, object_id: str) -> None:
        """Remove a node, its edges, and its trajectory entries.

        This is the structural half of a transaction rollback: it undoes the
        graph effect of one cognitive step so the SQLite state matches the
        filesystem after a ``git reset``. Edges are removed explicitly (belt and
        suspenders alongside the ON DELETE CASCADE foreign key).
        """
        self._conn.execute(
            "DELETE FROM edges WHERE from_id = ? OR to_id = ?", (object_id, object_id)
        )
        self._conn.execute("DELETE FROM nodes WHERE id = ?", (object_id,))
        self._conn.execute("DELETE FROM trajectory WHERE object_id = ?", (object_id,))
        self._conn.commit()

    # -- trajectory log ----------------------------------------------------- #
    def log(
        self,
        agent: str,
        action: str,
        status: str,
        *,
        context_id: Optional[str] = None,
        object_kind: Optional[str] = None,
        object_id: Optional[str] = None,
        detail: Optional[str] = None,
    ) -> int:
        """Append one cognitive-trajectory entry. Returns its seq number.

        This is the "Agent X, in context Y, created claim Z" record. Together
        with node/edge timestamps it gives memory a timeline a vector store
        cannot.
        """
        cur = self._conn.execute(
            "INSERT INTO trajectory(ts, agent, context_id, action, object_kind, "
            "object_id, status, detail) VALUES (?,?,?,?,?,?,?,?)",
            (_now(), agent, context_id, action, object_kind, object_id, status, detail),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def trajectory(self, limit: Optional[int] = None) -> list[TrajectoryEntry]:
        sql = "SELECT * FROM trajectory ORDER BY seq"
        if limit is not None:
            sql += f" DESC LIMIT {int(limit)}"
        rows = self._conn.execute(sql).fetchall()
        entries = [_row_to_traj(r) for r in rows]
        return list(reversed(entries)) if limit is not None else entries


def _row_to_node(row: sqlite3.Row) -> Node:
    return Node(row["id"], row["kind"], row["context_id"], row["path"], row["created_at"])


def _row_to_traj(row: sqlite3.Row) -> TrajectoryEntry:
    return TrajectoryEntry(
        seq=row["seq"],
        ts=row["ts"],
        agent=row["agent"],
        context_id=row["context_id"],
        action=row["action"],
        object_kind=row["object_kind"],
        object_id=row["object_id"],
        status=row["status"],
        detail=row["detail"],
    )
