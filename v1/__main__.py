"""CLI entrypoint for the FPF orchestrator.

    python -m v1 run "<task>"            # live run via Claude (needs ANTHROPIC_API_KEY)
    python -m v1 run "<task>" --demo     # offline run with a scripted policy
    python -m v1 run "<task>" --memory ./mem   # persist memory to a directory

Prints the cognitive trajectory: each move, whether it was accepted, the commit
sha, and the final reasoning graph the agent built.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from datetime import datetime, timedelta

from .core import Task
from .memory import LexicalSemanticIndex
from .policy import FINISH, Planner, ScriptedPolicy

_NOW = datetime(2026, 6, 13)

# A canned, offline example so the loop is runnable without an API key.
_DEMO_MOVES = ["BoundedContext", "Claim", "Evidence", "DecisionRecord", FINISH]
_DEMO_OBJECTS = {
    "BoundedContext": {"id": "Proj.Demo", "invariants": ["terms are local to Proj.Demo"]},
    "Claim": {
        "id": "C1",
        "statement": "Postgres meets our latency and durability needs",
        "context_id": "Proj.Demo",
    },
    "Evidence": {
        "id": "E1",
        "kind": "empirical",
        "target_claim_id": "C1",
        "claim_scope": "p95 write latency on staging, 2026-Q2",
        "timespan": {
            "valid_from": _NOW.isoformat(),
            "valid_until": (_NOW + timedelta(days=30)).isoformat(),
        },
        "source": "bench-run-demo",
    },
    "DecisionRecord": {
        "id": "D1",
        "context_id": "Proj.Demo",
        "decision_subject": "primary datastore",
        "option_set": ["postgres", "mysql", "dynamodb"],
        "choice_rule": "lowest p95 under durability constraint",
        "chosen": "postgres",
        "supporting_claim_ids": ["C1"],
    },
}


def _build_policy(args: argparse.Namespace):
    if args.demo:
        return ScriptedPolicy(_DEMO_MOVES, _DEMO_OBJECTS)

    if args.provider == "wavespeed":
        try:
            from .policy import WaveSpeedPolicy

            models = tuple(args.model.split(",")) if args.model else None
            return WaveSpeedPolicy(models=models)
        except Exception as exc:
            print(f"error: could not start WaveSpeedPolicy ({exc}).", file=sys.stderr)
            print("Hint: `pip install openai`; key in v1/policy/_secret.py or "
                  "FPF_LLM_API_KEY.", file=sys.stderr)
            raise SystemExit(2)

    if args.provider == "anthropic":
        try:
            from .policy import AnthropicPolicy

            return AnthropicPolicy()
        except Exception as exc:  # missing SDK or key
            print(f"error: could not start AnthropicPolicy ({exc}).", file=sys.stderr)
            print("Hint: --demo, or `pip install anthropic` + ANTHROPIC_API_KEY.",
                  file=sys.stderr)
            raise SystemExit(2)

    # openai-compatible (DeepSeek / Qwen / Kimi / GLM / gateway)
    base_url = args.base_url or os.environ.get("FPF_LLM_BASE_URL")
    api_key = os.environ.get("FPF_LLM_API_KEY")
    model = args.model or os.environ.get("FPF_LLM_MODEL")
    missing = [
        name
        for name, val in (
            ("--base-url / FPF_LLM_BASE_URL", base_url),
            ("FPF_LLM_API_KEY (env only)", api_key),
            ("--model / FPF_LLM_MODEL", model),
        )
        if not val
    ]
    if missing:
        print("error: openai-compat provider needs: " + ", ".join(missing),
              file=sys.stderr)
        raise SystemExit(2)
    try:
        from .policy import OpenAICompatPolicy

        return OpenAICompatPolicy(model=model, base_url=base_url, api_key=api_key)
    except Exception as exc:
        print(f"error: could not start OpenAICompatPolicy ({exc}).", file=sys.stderr)
        print("Hint: `pip install openai`.", file=sys.stderr)
        raise SystemExit(2)


def _run(args: argparse.Namespace) -> int:
    memory_root = args.memory or tempfile.mkdtemp(prefix="fpf-")
    policy = _build_policy(args)
    planner = Planner(memory_root, policy, semantic=LexicalSemanticIndex())
    task = Task(id=args.task_id, description=args.task)

    print(f"# FPF run — task {task.id!r}: {task.description}")
    print(f"# memory: {memory_root}\n")

    result = planner.run(task)

    for i, step in enumerate(result.history, 1):
        mark = "ok " if step.ok else "REJ"
        obj = step.object_id or "(finish)"
        sha = (step.sha or "")[:8]
        line = f"{i:>2}. [{mark}] {obj:<14} {step.step_before.value}->{step.step_after.value} {sha}"
        if not step.ok:
            why = step.violations[0].detail if step.violations else (
                step.verification.detail if step.verification else "?"
            )
            line += f"  <- {why}"
        print(line)

    print()
    served_by = getattr(policy, "last_model", None)
    if served_by:
        print(f"served by: {served_by}")
    print(f"result: {'DONE' if result.ok else 'INCOMPLETE'} "
          f"({result.steps_taken} moves, final phase {result.final_step.value})")
    if result.aborted_reason:
        print(f"reason: {result.aborted_reason}")

    g = planner.orch.memory.graph
    traj = g.trajectory()
    if traj:
        print("\nreasoning graph (nodes):")
        seen = []
        for entry in traj:
            if entry.object_id and entry.object_id not in seen:
                seen.append(entry.object_id)
                node = g.get_node(entry.object_id)
                if node:
                    print(f"  - {node.kind}:{node.id}  in {node.context_id or '-'}")
    return 0 if result.ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="v1", description="FPF orchestrator CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="run the reasoning loop on a task")
    run.add_argument("task", help="task description")
    run.add_argument("--task-id", default="task-1", help="stable task id")
    run.add_argument("--memory", help="memory directory (default: a temp dir)")
    run.add_argument("--demo", action="store_true", help="offline scripted policy")
    run.add_argument(
        "--provider",
        choices=["wavespeed", "anthropic", "openai-compat"],
        default="wavespeed",
        help="LLM backend (default: wavespeed)",
    )
    run.add_argument("--model", help="model id, or comma-list for wavespeed fallback")
    run.add_argument("--base-url", help="base url for --provider openai-compat")
    run.set_defaults(func=_run)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
