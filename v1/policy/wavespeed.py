"""WaveSpeed policy — top Chinese models with automatic fallback.

WaveSpeed (https://llm.wavespeed.ai/v1) is an OpenAI-compatible aggregator. This
policy tries a list of top Chinese models in order — Qwen, then DeepSeek, then
Kimi — and falls through to the next on any error, so a single model being down
or rate-limited doesn't stop the run.

The API key is read from the gitignored ``_secret.py`` (hardcoded for zero-setup
local runs) or the ``FPF_LLM_API_KEY`` env var. Model ids follow WaveSpeed's
``provider/model`` convention; adjust ``DEFAULT_MODELS`` to whatever ids your
account exposes (the run prints which model answered).
"""

from __future__ import annotations

import os
from typing import Any, Optional

from ..core.orchestrator import Task
from ..core.state_manager import Step
from ..core.validator import KnowledgeBase, Violation
from .openai_compat import OpenAICompatPolicy
from .policy import Move

BASE_URL = "https://llm.wavespeed.ai/v1"

# Ordered fallback — top Chinese models. Edit to match your WaveSpeed catalog.
DEFAULT_MODELS = (
    "qwen/qwen3-max",
    "deepseek/deepseek-v3.2",
    "moonshotai/kimi-k2.6",
)


def _resolve_key() -> str:
    key = os.environ.get("FPF_LLM_API_KEY")
    if key:
        return key
    try:
        from ._secret import WAVESPEED_API_KEY

        return WAVESPEED_API_KEY
    except Exception as exc:  # pragma: no cover - misconfiguration
        raise RuntimeError(
            "no WaveSpeed key: set FPF_LLM_API_KEY or fill v1/policy/_secret.py"
        ) from exc


class WaveSpeedPolicy:
    """Chooses moves via WaveSpeed, falling back across models on failure."""

    def __init__(
        self,
        *,
        models: Optional[tuple[str, ...]] = None,
        api_key: Optional[str] = None,
        base_url: str = BASE_URL,
        client: Any = None,
    ) -> None:
        self.models = tuple(models or _env_models() or DEFAULT_MODELS)
        key = api_key or _resolve_key()
        # One OpenAICompatPolicy per candidate model (shared client if injected).
        self._backends = [
            OpenAICompatPolicy(model=m, base_url=base_url, api_key=key, client=client)
            for m in self.models
        ]
        self.last_model: Optional[str] = None

    def choose(
        self,
        *,
        task: Task,
        step: Step,
        allowed_kinds: set[str],
        can_finish: bool,
        kb: KnowledgeBase,
        recall: Optional[list[str]] = None,
        feedback: Optional[list[Violation]] = None,
    ) -> Move:
        errors = []
        for model, backend in zip(self.models, self._backends):
            try:
                move = backend.choose(
                    task=task,
                    step=step,
                    allowed_kinds=allowed_kinds,
                    can_finish=can_finish,
                    kb=kb,
                    recall=recall,
                    feedback=feedback,
                )
                self.last_model = model
                return move
            except Exception as exc:  # try the next model
                errors.append(f"{model}: {exc}")
        raise RuntimeError("all WaveSpeed models failed:\n  " + "\n  ".join(errors))


def _env_models() -> Optional[tuple[str, ...]]:
    raw = os.environ.get("FPF_WS_MODELS")
    if not raw:
        return None
    return tuple(m.strip() for m in raw.split(",") if m.strip())
