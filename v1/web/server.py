"""FPF Studio — FastAPI backend for the reasoning UI.

Wraps the Planner/Orchestrator behind a small HTTP API and serves the static
frontend. A run executes in a background thread; each move is pushed onto a
queue and streamed to the browser over SSE, so the human watches the agent build
its reasoning live — including the firewall rejecting bad moves.

Endpoints
    POST /api/runs                 -> start a run, returns {run_id}
    GET  /api/runs/{id}/stream     -> SSE: step / done / error events
    GET  /api/runs/{id}/graph      -> {nodes, edges} reasoning graph
    GET  /api/runs/{id}/object/{o} -> the FPF object behind a node
    GET  /                         -> the studio UI
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
from fastapi.responses import FileResponse, StreamingResponse

from ..core.orchestrator import StepResult, Task
from ..memory import LexicalSemanticIndex
from ..policy import FINISH, Planner, ScriptedPolicy

_STATIC = Path(__file__).parent / "static"

app = FastAPI(title="FPF Studio")


@dataclass
class Run:
    id: str
    task: str
    provider: str
    q: "queue.Queue[Optional[dict]]" = field(default_factory=queue.Queue)
    planner: Optional[Planner] = None
    done: bool = False
    served_by: Optional[str] = None


_RUNS: dict[str, Run] = {}


def _step_event(sr: StepResult) -> dict:
    return {
        "type": "step",
        "ok": sr.ok,
        "kind": sr.kind,
        "object_id": sr.object_id,
        "phase": f"{sr.step_before.value}→{sr.step_after.value}",
        "sha": (sr.sha or "")[:8],
        "rolled_back": sr.rolled_back,
        "reason": (
            sr.violations[0].detail
            if sr.violations
            else (sr.verification.detail if (sr.verification and not sr.ok) else None)
        ),
    }


def _build_policy(provider: str, model: Optional[str]):
    if provider == "demo":
        from ..__main__ import _DEMO_MOVES, _DEMO_OBJECTS

        return ScriptedPolicy(_DEMO_MOVES, _DEMO_OBJECTS)
    if provider == "wavespeed":
        from ..policy import WaveSpeedPolicy

        models = tuple(m.strip() for m in model.split(",")) if model else None
        return WaveSpeedPolicy(models=models)
    if provider == "anthropic":
        from ..policy import AnthropicPolicy

        return AnthropicPolicy()
    raise ValueError(f"unknown provider {provider!r}")


def _worker(run: Run, model: Optional[str], task_id: str) -> None:
    try:
        policy = _build_policy(run.provider, model)
        root = tempfile.mkdtemp(prefix=f"fpf-{run.id[:8]}-")
        run.planner = Planner(root, policy, semantic=LexicalSemanticIndex())
        result = run.planner.run(
            Task(id=task_id, description=run.task),
            on_step=lambda sr: run.q.put(_step_event(sr)),
        )
        run.served_by = getattr(policy, "last_model", None)
        run.q.put(
            {
                "type": "done",
                "ok": result.ok,
                "final_phase": result.final_step.value,
                "steps": result.steps_taken,
                "served_by": run.served_by,
                "reason": result.aborted_reason,
            }
        )
    except Exception as exc:  # surface failures to the UI
        run.q.put({"type": "error", "message": str(exc)})
    finally:
        run.done = True
        run.q.put(None)  # sentinel


@app.post("/api/runs")
def start_run(body: dict[str, Any]) -> dict[str, str]:
    task = (body.get("task") or "").strip()
    if not task:
        raise HTTPException(400, "task is required")
    run = Run(id=uuid.uuid4().hex, task=task, provider=body.get("provider", "demo"))
    _RUNS[run.id] = run
    threading.Thread(
        target=_worker,
        args=(run, body.get("model"), body.get("task_id", "task-1")),
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
    if run is None or run.planner is None:
        raise HTTPException(404, "no graph yet")
    g = run.planner.orch.memory.graph
    nodes = [
        {"id": n.id, "kind": n.kind, "context": n.context_id} for n in g.all_nodes()
    ]
    edges = [
        {"source": e.from_id, "target": e.to_id, "rel": e.rel} for e in g.all_edges()
    ]
    return {"nodes": nodes, "edges": edges}


@app.get("/api/runs/{run_id}/object/{object_id}")
def get_object(run_id: str, object_id: str) -> dict[str, Any]:
    run = _RUNS.get(run_id)
    if run is None or run.planner is None:
        raise HTTPException(404, "no such run")
    node = run.planner.orch.memory.graph.get_node(object_id)
    if node is None or not node.path:
        raise HTTPException(404, "no such object")
    obj = run.planner.orch.memory.md.read(node.path)
    return {"kind": node.kind, "payload": obj.model_dump(mode="json")}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(_STATIC / "index.html")


@app.get("/app.js")
def appjs() -> FileResponse:
    return FileResponse(_STATIC / "app.js")
