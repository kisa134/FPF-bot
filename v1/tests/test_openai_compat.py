"""Contract for the OpenAI-compatible and WaveSpeed policies (stub client)."""

from __future__ import annotations

import json
import unittest

from v1.core import Task
from v1.core.state_manager import Step
from v1.core.validator import KnowledgeBase
from v1.policy import FINISH, OpenAICompatPolicy, WaveSpeedPolicy

CTX = {"id": "Proj.Alpha", "invariants": ["terms are local"]}


class _Fn:
    def __init__(self, name, args):
        self.name = name
        self.arguments = json.dumps(args)


class _ToolCall:
    def __init__(self, name, args):
        self.function = _Fn(name, args)


class _Msg:
    def __init__(self, name, args):
        self.tool_calls = [_ToolCall(name, args)]


class _Choice:
    def __init__(self, name, args):
        self.message = _Msg(name, args)


class _Resp:
    def __init__(self, name, args):
        self.choices = [_Choice(name, args)]


class _Completions:
    def __init__(self, owner):
        self.owner = owner

    def create(self, **kwargs):
        self.owner.calls.append(kwargs)
        return self.owner.script(kwargs)


class _FakeOpenAI:
    """Returns a scripted tool call; ``script`` can raise to simulate failure."""

    def __init__(self, script):
        self.script = script
        self.calls = []
        self.chat = type("Chat", (), {"completions": _Completions(self)})()


class TestOpenAICompat(unittest.TestCase):
    def test_tool_call_is_parsed(self):
        client = _FakeOpenAI(lambda kw: _Resp("declare_bounded_context", CTX))
        policy = OpenAICompatPolicy(model="m", base_url="x", api_key="k", client=client)
        kind, raw = policy.choose(
            task=Task("t"),
            step=Step.FRAME,
            allowed_kinds={"BoundedContext"},
            can_finish=False,
            kb=KnowledgeBase(),
        )
        self.assertEqual((kind, raw), ("BoundedContext", CTX))
        # tools were offered as OpenAI functions with forced choice
        kw = client.calls[0]
        self.assertEqual(kw["tool_choice"], "required")
        self.assertEqual(kw["tools"][0]["type"], "function")

    def test_finish_tool_parsed(self):
        client = _FakeOpenAI(lambda kw: _Resp("finish_reasoning", {}))
        policy = OpenAICompatPolicy(model="m", base_url="x", api_key="k", client=client)
        kind, _ = policy.choose(
            task=Task("t"),
            step=Step.WORK,
            allowed_kinds={"Claim"},
            can_finish=True,
            kb=KnowledgeBase(),
        )
        self.assertEqual(kind, FINISH)


class TestWaveSpeedFallback(unittest.TestCase):
    def test_falls_through_to_next_model(self):
        state = {"n": 0}

        def script(kw):
            state["n"] += 1
            if state["n"] == 1:
                raise RuntimeError("first model down")
            return _Resp("declare_bounded_context", CTX)

        client = _FakeOpenAI(script)
        policy = WaveSpeedPolicy(
            models=("qwen/a", "deepseek/b", "moonshotai/c"),
            api_key="k",
            client=client,
        )
        kind, raw = policy.choose(
            task=Task("t"),
            step=Step.FRAME,
            allowed_kinds={"BoundedContext"},
            can_finish=False,
            kb=KnowledgeBase(),
        )
        self.assertEqual((kind, raw), ("BoundedContext", CTX))
        self.assertEqual(policy.last_model, "deepseek/b")  # first failed, second won

    def test_all_failing_raises(self):
        def script(kw):
            raise RuntimeError("down")

        policy = WaveSpeedPolicy(
            models=("qwen/a", "deepseek/b"), api_key="k", client=_FakeOpenAI(script)
        )
        with self.assertRaises(RuntimeError):
            policy.choose(
                task=Task("t"),
                step=Step.FRAME,
                allowed_kinds={"BoundedContext"},
                can_finish=False,
                kb=KnowledgeBase(),
            )


if __name__ == "__main__":
    unittest.main()
