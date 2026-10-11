"""``jarvis listen``: wake word / claps, then a continuous spoken conversation."""

from __future__ import annotations

from unittest import mock

import click
import pytest
from click.testing import CliRunner

from openjarvis.cli import cli
from openjarvis.cli.listen_cmd import (
    DEFAULT_VOICE_TOOLS,
    FIRST_REQUEST_WAIT,
    MAX_HISTORY_MESSAGES,
    _build_triggers,
    is_goodbye,
    run_conversation,
)
from openjarvis.core.config import JarvisConfig
from openjarvis.core.types import Role

EXIT = object()


@pytest.mark.parametrize(
    "phrase",
    [
        "Tchau!",
        "Obrigado, Jarvis.",
        "obrigada",
        "Valeu, é só isso",
        "Muito obrigado",
        "Pode parar",
        "Thank you",
        "That's all",
        "Goodbye",
    ],
)
def test_goodbyes_end_the_conversation(phrase: str) -> None:
    assert is_goodbye(phrase)


@pytest.mark.parametrize(
    "phrase",
    [
        "",
        "Abre o Safari",
        "que horas são",
        "obrigado, e qual é a previsão do tempo",
        "pode parar a música e abrir o Safari",
        "stop the music and open Safari",
    ],
)
def test_requests_that_mention_a_goodbye_word_keep_going(phrase: str) -> None:
    assert not is_goodbye(phrase)


class Harness:
    """Scripted microphone + recorder of what was spoken and asked."""

    def __init__(self, heard: list, answers: list[str] | None = None) -> None:
        self.heard = list(heard)
        self.answers = list(answers or [])
        self.waits: list[float] = []
        self.spoken: list[str] = []
        self.asked: list[tuple[str, list[tuple[Role, str]]]] = []

    def record(self, wait: float):
        self.waits.append(wait)
        return self.heard.pop(0)

    def ask(self, text: str, history) -> str:
        self.asked.append((text, [(m.role, m.content) for m in history]))
        return self.answers.pop(0) if self.answers else f"resposta {len(self.asked)}"

    def run(self, **overrides) -> bool:
        options = dict(
            greeting="Pois não, Julio?",
            goodbye="Até logo.",
            ask=self.ask,
            record=self.record,
            speak=self.spoken.append,
            exit_signal=EXIT,
            follow_up_seconds=8.0,
        )
        options.update(overrides)
        return run_conversation(**options)


def test_one_wake_up_serves_several_requests_with_context() -> None:
    h = Harness(["que horas são", "e amanhã?", None])
    assert h.run() is True

    assert h.spoken == ["Pois não, Julio?", "resposta 1", "resposta 2"]
    # The follow-up sees the first exchange; the first request sees nothing.
    assert h.asked[0][1] == []
    assert h.asked[1][1] == [
        (Role.USER, "que horas são"),
        (Role.ASSISTANT, "resposta 1"),
    ]
    # First request gets the longer wait, follow-ups the configured window.
    assert h.waits == [FIRST_REQUEST_WAIT, 8.0, 8.0]


def test_silence_returns_to_standby_without_asking() -> None:
    h = Harness([None])
    assert h.run() is True
    assert h.asked == []
    assert h.spoken == ["Pois não, Julio?"]


def test_goodbye_says_goodbye_and_does_not_ask_the_model() -> None:
    h = Harness(["que horas são", "obrigado"])
    assert h.run() is True
    assert h.spoken == ["Pois não, Julio?", "resposta 1", "Até logo."]
    assert len(h.asked) == 1


def test_a_listening_failure_stops_the_program() -> None:
    h = Harness([EXIT])
    assert h.run() is False


def test_zero_follow_up_means_one_question_per_wake_up() -> None:
    h = Harness(["que horas são"])
    assert h.run(follow_up_seconds=0) is True
    assert len(h.asked) == 1 and h.waits == [FIRST_REQUEST_WAIT]


def test_history_is_capped() -> None:
    turns = [f"pergunta {i}" for i in range(MAX_HISTORY_MESSAGES)]
    h = Harness([*turns, None])
    h.run()
    assert len(h.asked[-1][1]) == MAX_HISTORY_MESSAGES


def _config(language: str = "pt", wake: str = "both") -> JarvisConfig:
    config = JarvisConfig()
    config.digest.honorific = "Julio"
    config.speech.language = language
    config.speech.wake = wake
    config.speech.follow_up_seconds = 5.0
    return config


def _invoke(config: JarvisConfig, *args: str, heard=("status", None), triggers=None):
    spoken: list[str] = []
    fake_jarvis = mock.MagicMock()
    fake_jarvis.ask.return_value = "Tudo certo."
    build = mock.MagicMock(return_value=("both", object()))
    with (
        mock.patch("openjarvis.core.config.load_config", return_value=config),
        mock.patch("openjarvis.cli.listen_cmd._build_triggers", build),
        mock.patch("openjarvis.cli.listen_cmd._warm_up_voice"),
        mock.patch(
            "openjarvis.speech.trigger.wait_for_trigger",
            side_effect=list(triggers or ["jarvis"]),
        ),
        mock.patch("openjarvis.cli._voice_chat.record_voice", side_effect=list(heard)),
        mock.patch(
            "openjarvis.cli._voice_chat.speak_streaming",
            side_effect=lambda line, *a, **k: spoken.append(line),
        ),
        mock.patch("openjarvis.sdk.Jarvis", return_value=fake_jarvis),
    ):
        result = CliRunner().invoke(cli, ["listen", "--once", *args])
    return result, spoken, fake_jarvis, build


def test_listen_runs_a_portuguese_conversation_with_tools_and_history() -> None:
    result, spoken, jarvis, _ = _invoke(_config())

    assert result.exit_code == 0, result.output
    assert "diga" in result.output and "bata duas palmas" in result.output
    assert spoken == ["Pois não, Julio?", "Tudo certo."]
    (query,), kwargs = jarvis.ask.call_args
    assert "português do Brasil" in query and query.endswith("status")
    assert kwargs["agent"] == "orchestrator"
    assert kwargs["tools"] == DEFAULT_VOICE_TOOLS
    assert kwargs["history"] == []
    jarvis.close.assert_called_once()


def test_listen_speaks_english_by_default() -> None:
    result, spoken, _, _ = _invoke(_config(language=""))
    assert result.exit_code == 0, result.output
    assert spoken[0] == "Yes, Julio?"


def test_wake_mode_comes_from_config_unless_overridden() -> None:
    _, _, _, build = _invoke(_config(wake="jarvis"))
    assert build.call_args.args[0] == "jarvis"

    _, _, _, build = _invoke(_config(wake="jarvis"), "--wake", "clap")
    assert build.call_args.args[0] == "clap"


def test_tools_can_be_overridden_or_disabled() -> None:
    _, _, jarvis, _ = _invoke(_config(), "--tools", "web_search, think")
    assert jarvis.ask.call_args.kwargs["tools"] == ["web_search", "think"]

    _, _, jarvis, _ = _invoke(_config(), "--tools", "")
    assert jarvis.ask.call_args.kwargs["tools"] is None
    assert jarvis.ask.call_args.kwargs["agent"] is None


def test_a_model_failure_is_spoken_not_raised() -> None:
    config = _config()
    spoken: list[str] = []
    jarvis = mock.MagicMock()
    jarvis.ask.side_effect = RuntimeError("engine down")
    with (
        mock.patch("openjarvis.core.config.load_config", return_value=config),
        mock.patch(
            "openjarvis.cli.listen_cmd._build_triggers",
            return_value=("both", object()),
        ),
        mock.patch("openjarvis.cli.listen_cmd._warm_up_voice"),
        mock.patch("openjarvis.speech.trigger.wait_for_trigger", return_value="jarvis"),
        mock.patch(
            "openjarvis.cli._voice_chat.record_voice", side_effect=["status", None]
        ),
        mock.patch(
            "openjarvis.cli._voice_chat.speak_streaming",
            side_effect=lambda line, *a, **k: spoken.append(line),
        ),
        mock.patch("openjarvis.sdk.Jarvis", return_value=jarvis),
    ):
        result = CliRunner().invoke(cli, ["listen", "--once"])

    assert result.exit_code == 0, result.output
    assert spoken[-1] == "Desculpe, não consegui falar com o modelo."


def test_both_degrades_to_claps_when_the_wake_model_is_missing() -> None:
    console = mock.MagicMock()
    with mock.patch(
        "openjarvis.speech.trigger.WakeWordDetector",
        side_effect=RuntimeError("needs openwakeword."),
    ):
        mode, _ = _build_triggers("both", 3000.0, 0.5, console)
    assert mode == "clap"
    assert "claps only" in console.print.call_args.args[0]


def test_jarvis_only_fails_loudly_when_the_wake_model_is_missing() -> None:
    with mock.patch(
        "openjarvis.speech.trigger.WakeWordDetector",
        side_effect=RuntimeError("needs openwakeword."),
    ):
        with pytest.raises(click.ClickException, match="openwakeword"):
            _build_triggers("jarvis", 3000.0, 0.5, mock.MagicMock())
