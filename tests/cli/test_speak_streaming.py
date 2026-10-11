"""speak_streaming synthesizes the next sentence while the current one plays."""

import threading
from types import SimpleNamespace
from unittest import mock

from openjarvis.cli._voice_chat import VoiceSession, speak_streaming
from openjarvis.core.config import JarvisConfig

TEXT = (
    "Abri o Safari para você agora mesmo. "
    "A previsão do tempo é de sol amanhã. "
    "Posso ajudar com mais alguma coisa hoje?"
)


class FakeTTS:
    backend_id = "kokoro"

    def __init__(self, events: list[str], fail_on: str | None = None) -> None:
        self.events = events
        self.fail_on = fail_on

    def synthesize(self, text: str, **kwargs):
        if self.fail_on and self.fail_on in text:
            raise RuntimeError("synthesis failed")
        self.events.append(f"synth:{text.split()[0]}")
        return SimpleNamespace(audio=text.encode(), sample_rate=24000)


def _session(backend) -> VoiceSession:
    session = VoiceSession(JarvisConfig())
    session._tts_backend = backend
    session._voice_prefs = ("kokoro", "pm_alex", 1.0)
    return session


def test_sentences_play_in_order() -> None:
    events: list[str] = []
    played: list[str] = []

    def play(audio: bytes, sample_rate: int = 0) -> None:
        played.append(audio.decode().split()[0])

    with mock.patch("openjarvis.speech.voice_io.play_wav", side_effect=play):
        speak_streaming(TEXT, mock.MagicMock(), _session(FakeTTS(events)))

    assert played == ["Abri", "A", "Posso"]


def test_next_sentence_is_synthesized_while_the_current_one_plays() -> None:
    events: list[str] = []
    second_synth_started = threading.Event()

    class SignallingTTS(FakeTTS):
        def synthesize(self, text: str, **kwargs):
            result = super().synthesize(text, **kwargs)
            if text.startswith("A previsão"):
                second_synth_started.set()
            return result

    overlapped: list[bool] = []

    def play(audio: bytes, sample_rate: int = 0) -> None:
        if audio.decode().startswith("Abri"):
            # While sentence 1 "plays", sentence 2 must already be in flight.
            overlapped.append(second_synth_started.wait(timeout=2.0))

    with mock.patch("openjarvis.speech.voice_io.play_wav", side_effect=play):
        speak_streaming(TEXT, mock.MagicMock(), _session(SignallingTTS(events)))

    assert overlapped == [True]


def test_single_sentence_uses_the_plain_path() -> None:
    session = _session(FakeTTS([]))
    with mock.patch("openjarvis.cli._voice_chat.speak") as plain:
        speak_streaming("Pois não, Julio?", mock.MagicMock(), session)
    plain.assert_called_once()


def test_playback_failure_stops_the_synthesis_worker() -> None:
    events: list[str] = []
    before = threading.active_count()

    with mock.patch(
        "openjarvis.speech.voice_io.play_wav", side_effect=RuntimeError("no audio")
    ):
        try:
            speak_streaming(TEXT, mock.MagicMock(), _session(FakeTTS(events)))
        except RuntimeError:
            pass

    assert threading.active_count() <= before  # worker thread did not leak


def test_a_failed_sentence_does_not_block_the_rest() -> None:
    events: list[str] = []
    played: list[str] = []

    def play(audio: bytes, sample_rate: int = 0) -> None:
        played.append(audio.decode().split()[0])

    backend = FakeTTS(events, fail_on="previsão")
    with mock.patch("openjarvis.speech.voice_io.play_wav", side_effect=play):
        speak_streaming(TEXT, mock.MagicMock(), _session(backend))

    assert "Abri" in played
