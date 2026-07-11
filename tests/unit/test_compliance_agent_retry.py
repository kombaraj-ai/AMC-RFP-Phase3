"""Unit tests for `_RetryingComplianceAgent`'s StructuredOutputException retry.

Patches `Agent.stream_async` (the method the wrapper calls via `super()`) with
a fake async generator so this exercises the retry/rollback logic without any
real model or Ollama call - see CLAUDE.md "Bug #2" for why this retry exists.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from strands import Agent
from strands.types.exceptions import StructuredOutputException

from amc_orchestrator.agents.compliance_agent import _RetryingComplianceAgent


def _make_agent(max_attempts: int) -> _RetryingComplianceAgent:
    return _RetryingComplianceAgent(
        max_attempts=max_attempts,
        model="dummy",
        system_prompt="test system prompt",
        name="compliance_check",
    )


async def test_recovers_after_one_failure():
    agent = _make_agent(max_attempts=3)
    calls = {"count": 0}

    async def fake_stream_async(self, *args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise StructuredOutputException("model didn't call the tool")
        yield {"result": "ok"}

    with patch.object(Agent, "stream_async", fake_stream_async):
        events = [event async for event in agent.stream_async("hello")]

    assert events == [{"result": "ok"}]
    assert calls["count"] == 2


async def test_gives_up_after_max_attempts():
    agent = _make_agent(max_attempts=2)
    calls = {"count": 0}

    async def always_fails(self, *args, **kwargs):
        calls["count"] += 1
        raise StructuredOutputException("model didn't call the tool")
        yield  # pragma: no cover - makes this an async generator

    with patch.object(Agent, "stream_async", always_fails):
        with pytest.raises(StructuredOutputException):
            [event async for event in agent.stream_async("hello")]

    assert calls["count"] == 2


async def test_rolls_back_messages_before_retrying():
    agent = _make_agent(max_attempts=2)
    calls = {"count": 0}
    messages_seen_on_retry = []

    async def fake_stream_async(self, *args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            # Simulate the failed attempt polluting conversation history
            # before the exception is raised.
            self.messages.append({"role": "user", "content": [{"text": "forced prompt"}]})
            raise StructuredOutputException("model didn't call the tool")
        messages_seen_on_retry.append(list(self.messages))
        yield {"result": "ok"}

    with patch.object(Agent, "stream_async", fake_stream_async):
        [event async for event in agent.stream_async("hello")]

    assert messages_seen_on_retry == [[]]
