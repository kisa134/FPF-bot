"""Three-layer memory for the FPF agent.

- epistemic  : MarkdownStore  (Git-versioned .md working set)
- structural : ReasoningGraph (SQLite nodes/edges + trajectory log)
- semantic   : SemanticIndex  (optional protocol seam; no heavy dependency)
"""

from .graph import (
    Edge,
    Node,
    OntologyError,
    ReasoningGraph,
    TrajectoryEntry,
)
from .markdown_store import MarkdownStore
from .semantic import LexicalSemanticIndex
from .store import MemoryStore, SemanticIndex

__all__ = [
    "Edge",
    "Node",
    "OntologyError",
    "ReasoningGraph",
    "TrajectoryEntry",
    "MarkdownStore",
    "MemoryStore",
    "SemanticIndex",
    "LexicalSemanticIndex",
]
