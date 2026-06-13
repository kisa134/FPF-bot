"""MemoryStore -- the three-layer memory facade for the FPF agent.

Ties together:
  1. epistemic layer  -> MarkdownStore (Git-versioned .md working set)
  2. structural layer -> ReasoningGraph (SQLite nodes/edges + trajectory)
  3. semantic layer   -> SemanticIndex protocol (a seam; no heavy dep here)

The single entry point is :meth:`remember`, which takes a *validated* ontology
object and persists it coherently across layers, deriving the lawful FPF edges
from the object's own references. Git checkpoint/reset give the agent an
"undo to last sane state" -- amnesia protection at the memory layer.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Optional, Protocol, runtime_checkable

from ..core.ontology import (
    Claim,
    Commitment,
    DecisionRecord,
    Evidence,
    Method,
    PromiseContent,
)
from .graph import ReasoningGraph
from .markdown_store import MarkdownStore


@runtime_checkable
class SemanticIndex(Protocol):
    """Optional layer-3 seam: similarity recall over past reasoning.

    Intentionally a protocol, not an import. A real implementation may back
    onto sqlite-vss or any embedding store, but the orchestrator never depends
    on it -- recall is an enrichment, never a source of truth.
    """

    def index(self, object_id: str, text: str) -> None: ...
    def recall(self, query: str, k: int = 5) -> list[str]: ...


# How each object kind contributes edges, derived from its own fields.
def _edges_for(obj: Any) -> list[tuple[str, str, str]]:
    edges: list[tuple[str, str, str]] = []
    if isinstance(obj, Claim):
        edges.append((obj.id, "IN_CONTEXT", obj.context_id))
    elif isinstance(obj, Evidence):
        edges.append((obj.id, "SUPPORTS", obj.target_claim_id))
    elif isinstance(obj, DecisionRecord):
        edges.append((obj.id, "IN_CONTEXT", obj.context_id))
        for cid in obj.supporting_claim_ids:
            edges.append((obj.id, "RELIES_ON", cid))
    elif isinstance(obj, PromiseContent):
        edges.append((obj.id, "IN_CONTEXT", obj.context_id))
    elif isinstance(obj, Commitment):
        edges.append((obj.id, "IN_CONTEXT", obj.context_id))
        edges.append((obj.id, "PROMISES", obj.promise_content_id))
    elif isinstance(obj, Method):
        edges.append((obj.id, "IN_CONTEXT", obj.context_id))
    return edges


def _context_of(obj: Any) -> Optional[str]:
    return getattr(obj, "context_id", None)


class MemoryStore:
    """Coherent persistence of FPF objects across the three memory layers."""

    def __init__(
        self,
        root: str | Path,
        *,
        db_path: Optional[str] = None,
        semantic: Optional[SemanticIndex] = None,
    ) -> None:
        self.root = Path(root)
        self.md = MarkdownStore(self.root / "epistemic")
        self.graph = ReasoningGraph(db_path or str(self.root / "graph.db"))
        self.semantic = semantic

    def close(self) -> None:
        self.graph.close()

    # -- core operation ----------------------------------------------------- #
    def remember(self, obj: Any, *, agent: str = "orchestrator") -> Path:
        """Persist a validated object across all layers, atomically per layer.

        Order matters: write the markdown, register the node, then the edges.
        Edge creation re-checks FPF legality at the graph layer (defense in
        depth behind core/validator.py).
        """
        kind = type(obj).__name__
        path = self.md.write(obj)
        self.graph.add_node(obj.id, kind, context_id=_context_of(obj), path=str(path))
        for from_id, rel, to_id in _edges_for(obj):
            self.graph.add_edge(from_id, to_id, rel)

        if self.semantic is not None:
            self.semantic.index(obj.id, _summ(obj))

        self.graph.log(
            agent=agent,
            action="create",
            status="accepted",
            context_id=_context_of(obj),
            object_kind=kind,
            object_id=obj.id,
            detail=f"{agent} created {kind} {obj.id}",
        )
        return path

    # -- git-backed amnesia protection ------------------------------------- #
    def git(self, *args: str) -> str:
        """Run a git command inside the memory root; raises on failure."""
        res = subprocess.run(
            ["git", *args],
            cwd=self.root,
            capture_output=True,
            text=True,
        )
        if res.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed: {res.stderr.strip()}")
        return res.stdout.strip()

    def init_repo(self) -> None:
        if not (self.root / ".git").exists():
            self.git("init", "-q")
        # The structural db is managed manually (not versioned): git tracks only
        # the epistemic layer + artifacts, so a reset wipes hallucinated files
        # while the SQLite rollback is done explicitly via forget().
        gi = self.root / ".gitignore"
        if not gi.exists():
            gi.write_text("graph.db\ngraph.db-journal\ngraph.db-wal\n", encoding="utf-8")
        # Make commits succeed in isolated/CI environments (local scope only).
        self.git("config", "user.email", "agent@fpf.local")
        self.git("config", "user.name", "fpf-agent")
        self.git("config", "commit.gpgsign", "false")

    def forget(self, object_id: str) -> None:
        """Structural rollback: drop a node, its edges, and its trajectory."""
        self.graph.delete_object(object_id)

    def checkpoint(self, message: str, *, allow_empty: bool = False) -> str:
        """Commit the current reasoning state; returns the commit sha.

        ``allow_empty`` records a marker commit even when nothing changed on disk
        (used by phase transitions like finish, which mutate only state).
        """
        self.git("add", "-A")
        args = ["commit", "-q", "-m", message]
        if allow_empty:
            args.append("--allow-empty")
        self.git(*args)
        return self.git("rev-parse", "HEAD")

    def reset_to(self, sha: str) -> None:
        """Hard-reset working memory to a known-sane reasoning checkpoint."""
        self.git("reset", "--hard", sha)


def _summ(obj: Any) -> str:
    """A short text surface for optional semantic indexing."""
    for attr in ("statement", "decision_subject", "claim_scope", "id"):
        val = getattr(obj, attr, None)
        if val:
            return str(val)
    return obj.id
