"""Semantic recall over past reasoning — stdlib, no vector DB.

Fills the ``SemanticIndex`` seam (memory/store.py) with a working, dependency-free
implementation: lexical token-overlap recall with inverse-document weighting, so
rarer shared terms count for more than common ones. This is layer 3 of the
memory stack — recall is an *enrichment* ("have we reasoned about something like
this before?"), never a source of truth.

Swap-in path: a `sqlite-vss`/embedding implementation of the same two-method
protocol drops in unchanged. The lexical index is the zero-dependency floor.
"""

from __future__ import annotations

import math
import re
from collections import Counter

_TOKEN = re.compile(r"[a-z0-9]+")
# A few high-frequency words that carry little discriminative signal.
_STOP = frozenset(
    "the a an of to in on for and or is are be this that it with as by from".split()
)


def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOP]


class LexicalSemanticIndex:
    """In-memory token-overlap index implementing the SemanticIndex protocol."""

    def __init__(self) -> None:
        self._docs: dict[str, Counter[str]] = {}
        self._df: Counter[str] = Counter()  # document frequency per term

    def index(self, object_id: str, text: str) -> None:
        if object_id in self._docs:  # re-index: retract old df first
            for term in self._docs[object_id]:
                self._df[term] -= 1
        tf = Counter(_tokens(text))
        self._docs[object_id] = tf
        for term in tf:
            self._df[term] += 1

    def recall(self, query: str, k: int = 5) -> list[str]:
        """Return up to k object ids most lexically similar to the query."""
        q = Counter(_tokens(query))
        if not q or not self._docs:
            return []
        n = len(self._docs)
        scored: list[tuple[float, str]] = []
        for oid, tf in self._docs.items():
            score = 0.0
            for term, qcount in q.items():
                if term in tf:
                    # idf weighting: rarer shared terms matter more
                    idf = math.log(1 + n / (1 + self._df[term]))
                    score += qcount * tf[term] * idf
            if score > 0:
                scored.append((score, oid))
        scored.sort(key=lambda s: (-s[0], s[1]))
        return [oid for _, oid in scored[:k]]
