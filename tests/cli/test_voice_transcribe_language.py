"""record_voice passes [speech] language and ignores punctuation-only text."""

from types import SimpleNamespace
from unittest import mock

import pytest

from openjarvis.cli._voice_chat import VoiceSession, record_voice
from openjarvis.core.config import JarvisConfig


def _run(language: str, transcript: str):
    config = JarvisConfig()
    config.speech.language = language
    session = VoiceSession(config)
    backend = mock.MagicMock()
    backend.transcribe.return_value = SimpleNamespace(text=transcript)
    session._stt_backend, session._stt_resolved = backend, True
    with mock.patch(
        "openjarvis.speech.voice_io.record_until_silence", return_value=b"wav"
    ):
        result = record_voice(mock.MagicMock(), session)
    return result, backend


def test_language_forwarded_to_backend() -> None:
    result, backend = _run("pt", "Qual a minha agenda?")
    assert result == "Qual a minha agenda?"
    backend.transcribe.assert_called_once_with(b"wav", format="wav", language="pt")


def test_auto_detect_when_language_empty() -> None:
    _, backend = _run("", "hello")
    backend.transcribe.assert_called_once_with(b"wav", format="wav")


@pytest.mark.parametrize("noise", ["... ... ...", "", " . , "])
def test_punctuation_only_is_nothing_heard(noise: str) -> None:
    result, _ = _run("pt", noise)
    assert result is None
