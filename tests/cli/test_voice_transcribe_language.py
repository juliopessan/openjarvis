"""record_voice passes [speech] language, skips silence and punctuation-only text."""

from types import SimpleNamespace
from unittest import mock

import pytest

from openjarvis.cli._voice_chat import VoiceSession, record_voice
from openjarvis.core.config import JarvisConfig


def _run(language: str, transcript: str, *, heard_speech: bool = True, **kwargs):
    config = JarvisConfig()
    config.speech.language = language
    session = VoiceSession(config)
    backend = mock.MagicMock()
    backend.transcribe.return_value = SimpleNamespace(text=transcript)
    session._stt_backend, session._stt_resolved = backend, True
    with mock.patch(
        "openjarvis.speech.voice_io.record_utterance",
        return_value=(b"wav", heard_speech),
    ) as recorder:
        result = record_voice(mock.MagicMock(), session, **kwargs)
    return result, backend, recorder


def test_language_forwarded_to_backend() -> None:
    result, backend, _ = _run("pt", "Qual a minha agenda?")
    assert result == "Qual a minha agenda?"
    backend.transcribe.assert_called_once_with(b"wav", format="wav", language="pt")


def test_auto_detect_when_language_empty() -> None:
    _, backend, _ = _run("", "hello")
    backend.transcribe.assert_called_once_with(b"wav", format="wav")


@pytest.mark.parametrize("noise", ["... ... ...", "", " . , "])
def test_punctuation_only_is_nothing_heard(noise: str) -> None:
    result, _, _ = _run("pt", noise)
    assert result is None


def test_silence_is_never_sent_to_the_transcription_model() -> None:
    result, backend, _ = _run("pt", "Obrigado por assistir", heard_speech=False)
    assert result is None
    backend.transcribe.assert_not_called()


def test_wait_seconds_controls_how_long_it_waits_for_speech() -> None:
    _, _, recorder = _run("pt", "oi", wait_seconds=8.0)
    recorder.assert_called_once_with(startup_silence_seconds=8.0)


def test_default_wait_leaves_the_recorder_default() -> None:
    _, _, recorder = _run("pt", "oi")
    recorder.assert_called_once_with()
