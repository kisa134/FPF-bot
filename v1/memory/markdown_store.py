"""Epistemic memory: FPF objects as Git-friendly Markdown files.

Karpathy's instinct -- keep knowledge in plain Markdown -- is the right
external "hard drive" for an agent that reads and writes files directly. We
keep the files human-readable but make them *losslessly machine-parseable* by
embedding the object's canonical JSON in a fenced block. No YAML, no
third-party parser: stdlib ``json`` round-trips perfectly.

Layout (one file per object, grouped by kind):
    <root>/<Kind>/<id>.md

Each file: a short human header + a ```json fpf block carrying the full,
validated object payload. Parsing reads that block straight back into the
ontology types.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..core.ontology import BoundedContext, Claim, DecisionRecord, Evidence

_KINDS: dict[str, type] = {
    "BoundedContext": BoundedContext,
    "Claim": Claim,
    "Evidence": Evidence,
    "DecisionRecord": DecisionRecord,
}

# Matches the embedded payload block: ```json fpf ... ```
_BLOCK_RE = re.compile(r"```json fpf\n(.*?)\n```", re.DOTALL)


class MarkdownStore:
    """Reads/writes FPF objects as Markdown on disk."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, kind: str, object_id: str) -> Path:
        safe = object_id.replace("/", "_")
        return self.root / kind / f"{safe}.md"

    def write(self, obj: Any) -> Path:
        """Serialize a validated ontology object to its Markdown file."""
        kind = type(obj).__name__
        if kind not in _KINDS:
            raise TypeError(f"not a persistable FPF object: {kind}")
        payload = obj.model_dump(mode="json")
        path = self.path_for(kind, obj.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_render(kind, obj.id, payload), encoding="utf-8")
        return path

    def read(self, path: str | Path) -> Any:
        """Parse a Markdown file back into its typed ontology object."""
        text = Path(path).read_text(encoding="utf-8")
        match = _BLOCK_RE.search(text)
        if match is None:
            raise ValueError(f"no 'json fpf' payload block in {path}")
        payload = json.loads(match.group(1))
        kind = _infer_kind(path)
        return _KINDS[kind](**payload)

    def load_all(self) -> list[Any]:
        """Load every FPF object currently on disk (epistemic working set)."""
        out: list[Any] = []
        for kind in _KINDS:
            for md in sorted((self.root / kind).glob("*.md")) if (
                self.root / kind
            ).exists() else []:
                out.append(self.read(md))
        return out


def _render(kind: str, object_id: str, payload: dict[str, Any]) -> str:
    body = json.dumps(payload, indent=2, ensure_ascii=False)
    return (
        f"# {kind}: {object_id}\n\n"
        f"> FPF object stored as canonical JSON. Edit via the orchestrator, "
        f"not by hand, so validation invariants are preserved.\n\n"
        f"```json fpf\n{body}\n```\n"
    )


def _infer_kind(path: str | Path) -> str:
    kind = Path(path).parent.name
    if kind not in _KINDS:
        raise ValueError(f"cannot infer FPF kind from path {path!r}")
    return kind
