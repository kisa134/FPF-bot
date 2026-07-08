"""FPF Studio backend — streams a live FPF-Swarm (team of agents).

A run starts the Architect ↔ Censor team in a background thread; every agent
action (propose / veto / approve / commit) is streamed to the browser over SSE,
so you watch the team collaborate live and can open any agent. The shared
reasoning graph and FPF objects are exposed for inspection.
"""

from __future__ import annotations

import json
import queue
import tempfile
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from ..core.confidence import decision_confidence
from ..memory import LexicalSemanticIndex
from ..policy.swarm import AgentEvent, SwarmRunner

_STATIC = Path(__file__).parent / "static"
app = FastAPI(title="FPF Studio")
# Open CORS so a separate canvas frontend (future) can call the API + SSE.
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


@dataclass
class Run:
    id: str
    task: str
    provider: str
    q: "queue.Queue[Optional[dict]]" = field(default_factory=queue.Queue)
    runner: Optional[SwarmRunner] = None
    done: bool = False


_RUNS: dict[str, Run] = {}


class _PassCensor:
    """Fallback auditor (always approves) for providers without a live Censor."""

    def review(self, **_: Any) -> tuple[bool, str]:
        return True, "no independent censor configured — passed."


def _build_team(provider: str, model: Optional[str]):
    """Return (architect, censor, served_by_getter)."""
    if provider == "demo":
        from ..policy.swarm_demo import demo_swarm

        ds = demo_swarm()
        return ds, ds, lambda: "demo-swarm"

    if provider == "wavespeed":
        from ..policy.swarm import LLMCensor
        from ..policy.wavespeed import BASE_URL, WaveSpeedPolicy, _resolve_key

        key = _resolve_key()
        models = tuple(m.strip() for m in model.split(",")) if model else None
        architect = WaveSpeedPolicy(models=models)
        # Different model for the Censor → lower correlated blind spots.
        censor = LLMCensor(model="deepseek/deepseek-v3.2", base_url=BASE_URL, api_key=key)
        return architect, censor, lambda: architect.last_model

    if provider == "anthropic":
        from ..policy import AnthropicPolicy

        a = AnthropicPolicy()
        return a, _PassCensor(), lambda: "claude"

    raise ValueError(f"unknown provider {provider!r}")


def _evt(e: AgentEvent) -> dict:
    return {
        "type": "agent", "agent": e.agent, "role": e.role, "action": e.action,
        "content": e.content, "kind": e.kind, "object_id": e.object_id,
        "to": e.to, "ok": e.ok, "round": e.round,
    }


def _worker(run: Run, model: Optional[str], task_id: str) -> None:
    from ..core.orchestrator import Task

    try:
        architect, censor, served_by = _build_team(run.provider, model)
        root = tempfile.mkdtemp(prefix=f"fpf-{run.id[:8]}-")
        run.runner = SwarmRunner(root, architect, censor, semantic=LexicalSemanticIndex())
        result = run.runner.run(
            Task(id=task_id, description=run.task),
            on_event=lambda e: run.q.put(_evt(e)),
        )
        result.update({"type": "done", "served_by": served_by()})
        run.q.put(result)
    except Exception as exc:
        run.q.put({"type": "error", "message": str(exc)})
    finally:
        run.done = True
        run.q.put(None)


@app.post("/api/runs")
def start_run(body: dict[str, Any]) -> dict[str, str]:
    task = (body.get("task") or "").strip()
    if not task:
        raise HTTPException(400, "task is required")
    run = Run(id=uuid.uuid4().hex, task=task, provider=body.get("provider", "demo"))
    _RUNS[run.id] = run
    threading.Thread(
        target=_worker, args=(run, body.get("model"), body.get("task_id", "task-1")),
        daemon=True,
    ).start()
    return {"run_id": run.id}


@app.get("/api/runs/{run_id}/stream")
def stream(run_id: str) -> StreamingResponse:
    run = _RUNS.get(run_id)
    if run is None:
        raise HTTPException(404, "no such run")

    def gen():
        while True:
            item = run.q.get()
            if item is None:
                yield "event: end\ndata: {}\n\n"
                break
            yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/api/runs/{run_id}/graph")
def graph(run_id: str) -> dict[str, list]:
    run = _RUNS.get(run_id)
    if run is None or run.runner is None:
        raise HTTPException(404, "no graph yet")
    g = run.runner.orch.memory.graph
    return {
        "nodes": [{"id": n.id, "kind": n.kind, "context": n.context_id} for n in g.all_nodes()],
        "edges": [{"source": e.from_id, "target": e.to_id, "rel": e.rel} for e in g.all_edges()],
    }


@app.get("/api/runs/{run_id}/confidence")
def confidence(run_id: str) -> dict[str, Any]:
    run = _RUNS.get(run_id)
    if run is None or run.runner is None:
        raise HTTPException(404, "no such run")
    kb = run.runner.orch.sm.kb
    if not kb.decisions:
        return {"available": False}
    reports = {
        did: decision_confidence(d, kb).to_dict() for did, d in kb.decisions.items()
    }
    return {"available": True, "primary": next(iter(reports.values())), "by_decision": reports}


@app.get("/api/runs/{run_id}/object/{object_id}")
def get_object(run_id: str, object_id: str) -> dict[str, Any]:
    run = _RUNS.get(run_id)
    if run is None or run.runner is None:
        raise HTTPException(404, "no such run")
    node = run.runner.orch.memory.graph.get_node(object_id)
    if node is None or not node.path:
        raise HTTPException(404, "no such object")
    obj = run.runner.orch.memory.md.read(node.path)
    return {"kind": node.kind, "payload": obj.model_dump(mode="json")}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(_STATIC / "index.html")


@app.get("/app.js")
def appjs() -> FileResponse:
    return FileResponse(_STATIC / "app.js")
