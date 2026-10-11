"""Current Claude models reject sampling params and forced tool_choice."""

from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

import pytest

from openjarvis.core.registry import EngineRegistry
from openjarvis.core.types import Message, Role
from openjarvis.engine._stubs import ResponseFormat
from openjarvis.engine.cloud import CloudEngine


def _engine(monkeypatch: pytest.MonkeyPatch) -> tuple[CloudEngine, mock.MagicMock]:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    client = mock.MagicMock()
    client.messages.create.return_value = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="ok")],
        usage=SimpleNamespace(input_tokens=1, output_tokens=1),
        model="m",
        stop_reason="end_turn",
    )
    EngineRegistry.register_value("cloud", CloudEngine)
    engine = CloudEngine()
    engine._anthropic_client = client
    return engine, client


@pytest.mark.parametrize(
    ("model", "sends_temperature"),
    [
        ("claude-opus-5-5", False),
        ("claude-sonnet-5-5", False),
        ("claude-haiku-5-5", False),
        ("claude-opus-4-7", False),
        ("claude-sonnet-4-6", True),
        ("claude-haiku-4-5", True),
    ],
)
def test_temperature_only_sent_where_accepted(
    monkeypatch: pytest.MonkeyPatch, model: str, sends_temperature: bool
) -> None:
    engine, client = _engine(monkeypatch)
    engine.generate([Message(role=Role.USER, content="hi")], model=model)
    kwargs = client.messages.create.call_args.kwargs
    assert ("temperature" in kwargs) is sends_temperature


def test_structured_output_avoids_forced_tool_on_sonnet_5_5(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, client = _engine(monkeypatch)
    engine.generate(
        [Message(role=Role.USER, content="hi")],
        model="claude-sonnet-5-5",
        response_format=ResponseFormat(type="json_object", schema={"type": "object"}),
    )
    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["tool_choice"] == {"type": "auto"}
    assert "json_output" in kwargs["system"]
