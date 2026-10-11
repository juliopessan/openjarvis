"""Wake word + double clap triggers, driven by synthetic audio blocks."""

from __future__ import annotations

import numpy as np
import pytest

from openjarvis.speech.clap import ClapDetector
from openjarvis.speech.trigger import (
    BLOCK,
    WAKE_FRAME,
    TriggerListener,
    WakeWordDetector,
    normalize_mode,
    wait_for_trigger,
)


class FakeWakeModel:
    """Stands in for openWakeWord: scores whatever script it is given."""

    def __init__(self, scores: list[float]) -> None:
        self.scores = list(scores)
        self.frames: list[int] = []
        self.resets = 0

    def predict(self, frame: np.ndarray) -> dict[str, float]:
        self.frames.append(len(frame))
        return {"hey_jarvis_v0.1": self.scores.pop(0) if self.scores else 0.0}

    def reset(self) -> None:
        self.resets += 1


def _block(level: int = 100) -> bytes:
    return np.full(BLOCK, level, dtype=np.int16).tobytes()


def _feed(listener: TriggerListener, blocks: int, level: int = 100) -> list[str]:
    fired = []
    for _ in range(blocks):
        result = listener.feed(_block(level))
        if result:
            fired.append(result)
    return fired


def test_normalize_mode_defaults_to_clap() -> None:
    assert normalize_mode("JARVIS") == "jarvis"
    assert normalize_mode(" both ") == "both"
    assert normalize_mode("") == "clap"
    assert normalize_mode("whistle") == "clap"


def test_wake_model_receives_full_80ms_frames() -> None:
    model = FakeWakeModel([])
    listener = TriggerListener("jarvis", wake=WakeWordDetector(0.5, model))
    # 5 blocks of 512 = 2560 samples = exactly two 1280-sample frames.
    _feed(listener, 5)
    assert model.frames == [WAKE_FRAME, WAKE_FRAME]


def test_wake_word_fires_above_threshold_then_resets() -> None:
    model = FakeWakeModel([0.1, 0.9])
    listener = TriggerListener("jarvis", wake=WakeWordDetector(0.5, model))
    assert _feed(listener, 5) == ["jarvis"]
    assert model.resets == 1


def test_wake_word_below_threshold_stays_quiet() -> None:
    model = FakeWakeModel([0.2, 0.49, 0.3])
    listener = TriggerListener("jarvis", wake=WakeWordDetector(0.5, model))
    assert _feed(listener, 8) == []


def test_wake_cooldown_ignores_an_immediate_second_detection() -> None:
    model = FakeWakeModel([0.9, 0.9, 0.9])
    listener = TriggerListener("jarvis", wake=WakeWordDetector(0.5, model))
    # Three frames arrive within ~240 ms, well inside the 1.5 s cooldown.
    assert _feed(listener, 8) == ["jarvis"]


def test_clap_mode_never_consults_the_wake_model() -> None:
    model = FakeWakeModel([0.99] * 10)
    listener = TriggerListener("clap", wake=WakeWordDetector(0.5, model))
    assert _feed(listener, 20) == []
    assert model.frames == []


def test_jarvis_mode_ignores_claps() -> None:
    model = FakeWakeModel([])
    listener = TriggerListener("jarvis", wake=WakeWordDetector(0.5, model))
    quiet, loud = 100, 12000
    blocks = [quiet] * 30 + [loud] * 2 + [quiet] * 10 + [loud] * 2 + [quiet] * 30
    fired = [listener.feed(_block(level)) for level in blocks]
    assert not any(fired)


def test_clap_mode_fires_on_a_double_clap() -> None:
    listener = TriggerListener("clap", clap=ClapDetector())
    quiet, loud = 100, 12000
    blocks = [quiet] * 30 + [loud] * 2 + [quiet] * 10 + [loud] * 2 + [quiet] * 30
    fired = [r for r in (listener.feed(_block(lv)) for lv in blocks) if r]
    assert fired == ["clap"]


def test_both_mode_reports_whichever_fires() -> None:
    model = FakeWakeModel([0.0, 0.0, 0.95])
    listener = TriggerListener(
        "both", wake=WakeWordDetector(0.5, model), clap=ClapDetector()
    )
    assert _feed(listener, 8) == ["jarvis"]


def test_reset_clears_stale_audio_and_detector_state() -> None:
    model = FakeWakeModel([])
    listener = TriggerListener(
        "both", wake=WakeWordDetector(0.5, model), clap=ClapDetector(min_level=1234)
    )
    _feed(listener, 3)  # 1536 samples: one frame consumed, 256 left over
    listener.reset()

    assert len(listener._pending) == 0
    assert model.resets == 1
    assert listener._clap.min_level == 1234  # settings survive the reset


def test_wait_for_trigger_starts_from_a_clean_state() -> None:
    model = FakeWakeModel([])
    listener = TriggerListener("jarvis", wake=WakeWordDetector(0.5, model))
    _feed(listener, 3)

    class OneRead:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self, n: int):
            return _block(), False

    wait_for_trigger(listener, stream_factory=OneRead, should_stop=lambda: True)
    assert len(listener._pending) == 0


def test_wait_for_trigger_reads_until_one_fires() -> None:
    model = FakeWakeModel([0.0, 0.95])
    listener = TriggerListener("jarvis", wake=WakeWordDetector(0.5, model))

    class FakeStream:
        reads = 0

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self, n: int):
            FakeStream.reads += 1
            return _block(), False

    assert wait_for_trigger(listener, stream_factory=FakeStream) == "jarvis"
    assert FakeStream.reads == 5  # two 1280-sample frames' worth of blocks


def test_wait_for_trigger_honours_should_stop() -> None:
    listener = TriggerListener("clap", clap=ClapDetector())

    class FakeStream:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self, n: int):
            return _block(), False

    assert (
        wait_for_trigger(listener, stream_factory=FakeStream, should_stop=lambda: True)
        is None
    )


def test_real_bundled_model_ignores_silence_and_noise() -> None:
    pytest.importorskip("openwakeword")
    detector = WakeWordDetector(0.5)
    rng = np.random.default_rng(0)
    for samples in (
        np.zeros(16000 * 2, dtype=np.int16),
        rng.normal(0, 800, 16000 * 2).astype(np.int16),
    ):
        detector.reset()
        best = max(
            detector.score(samples[i : i + WAKE_FRAME])
            for i in range(0, len(samples) - WAKE_FRAME + 1, WAKE_FRAME)
        )
        assert best < 0.5


def test_real_bundled_model_detects_a_spoken_hey_jarvis(tmp_path) -> None:
    """Positive check; needs the espeak-ng binary to synthesize the phrase."""
    import shutil
    import subprocess
    import wave

    pytest.importorskip("openwakeword")
    espeak = shutil.which("espeak-ng")
    if espeak is None:
        pytest.skip("espeak-ng not installed")

    wav_path = tmp_path / "hey_jarvis.wav"
    subprocess.run(
        [espeak, "-v", "en-us", "-s", "140", "-w", str(wav_path), "Hey Jarvis"],
        check=True,
        capture_output=True,
    )
    with wave.open(str(wav_path)) as wav:
        rate = wav.getframerate()
        speech = np.frombuffer(wav.readframes(wav.getnframes()), dtype=np.int16)
    if rate != 16000:
        grid = np.linspace(0, len(speech) - 1, int(len(speech) * 16000 / rate))
        speech = np.interp(grid, np.arange(len(speech)), speech).astype(np.int16)
    audio = np.concatenate(
        [np.zeros(16000, np.int16), speech, np.zeros(16000, np.int16)]
    )

    listener = TriggerListener("jarvis", wake=WakeWordDetector(0.5))
    fired = [
        listener.feed(audio[i : i + BLOCK].tobytes())
        for i in range(0, len(audio) - BLOCK + 1, BLOCK)
    ]
    assert "jarvis" in fired
