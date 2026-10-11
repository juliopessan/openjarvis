"""Hands-free wake triggers: the "Jarvis" wake word and the double clap.

Both detectors listen to one shared microphone stream. The wake word uses the
``hey_jarvis`` model bundled with openWakeWord, so it runs fully offline and
needs no download. Decision logic lives in :class:`TriggerListener`, which only
consumes audio blocks, so it can be tested without a microphone.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

import numpy as np

from openjarvis.speech.clap import ClapDetector

WAKE_MODES = ("jarvis", "clap", "both")

SAMPLE_RATE = 16000
# 32 ms blocks resolve a clap's sharp edge; the wake model wants 80 ms frames,
# which the listener assembles from these blocks.
BLOCK = 512
WAKE_FRAME = 1280

_MODEL_NAME = "hey_jarvis"


def normalize_mode(mode: str) -> str:
    """Return a valid wake mode, falling back to ``"clap"`` (the old behavior)."""
    mode = (mode or "").strip().lower()
    return mode if mode in WAKE_MODES else "clap"


class WakeWordDetector:
    """Scores 80 ms frames with the bundled ``hey_jarvis`` model."""

    def __init__(self, threshold: float = 0.5, model: Any = None) -> None:
        self.threshold = threshold
        self._model = model if model is not None else self._load_model()

    @staticmethod
    def _load_model() -> Any:
        try:
            import openwakeword
            from openwakeword.model import Model
        except ImportError as exc:
            raise RuntimeError(
                "The 'Jarvis' wake word needs openwakeword. "
                "Install with: pip install 'OpenJarvis[voice]'"
            ) from exc
        paths = [
            p for p in openwakeword.get_pretrained_model_paths() if _MODEL_NAME in p
        ]
        if not paths:
            raise RuntimeError("openwakeword has no bundled hey_jarvis model.")
        return Model(wakeword_model_paths=paths)

    def score(self, frame: np.ndarray) -> float:
        """Highest wake-word score for one ``WAKE_FRAME``-sample int16 frame."""
        scores = self._model.predict(frame)
        return float(max(scores.values())) if scores else 0.0

    def reset(self) -> None:
        """Forget buffered audio so the same utterance is not detected twice."""
        self._model.reset()


class TriggerListener:
    """Feed mic blocks; ``feed`` names the trigger that fired, if any."""

    def __init__(
        self,
        mode: str = "both",
        *,
        wake: Optional[WakeWordDetector] = None,
        clap: Optional[ClapDetector] = None,
        wake_cooldown: float = 1.5,
        sample_rate: int = SAMPLE_RATE,
    ) -> None:
        self.mode = normalize_mode(mode)
        self._wake = wake if self.mode in ("jarvis", "both") else None
        self._clap = (clap or ClapDetector()) if self.mode in ("clap", "both") else None
        self._cooldown = wake_cooldown
        self._block_seconds = BLOCK / sample_rate
        self._t = 0.0
        self._quiet_until = 0.0
        self._pending = np.zeros(0, dtype=np.int16)

    def reset(self) -> None:
        """Drop buffered audio and detector state (call when standby resumes).

        A conversation can last minutes; stale audio must not be stitched onto
        the first blocks heard afterwards.
        """
        self._pending = np.zeros(0, dtype=np.int16)
        self._quiet_until = 0.0
        if self._wake is not None:
            self._wake.reset()
        if self._clap is not None:
            self._clap = ClapDetector(
                min_level=self._clap.min_level,
                rise_ratio=self._clap.rise_ratio,
                max_clap_seconds=self._clap.max_clap_seconds,
                min_gap=self._clap.min_gap,
                max_gap=self._clap.max_gap,
                cooldown=self._clap.cooldown,
            )

    def feed(self, block: bytes) -> Optional[str]:
        """Process one block of 16-bit mono PCM; return ``"jarvis"``/``"clap"``."""
        self._t += self._block_seconds
        samples = np.frombuffer(block, dtype=np.int16)

        fired: Optional[str] = None
        if self._clap is not None:
            rms = float(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))
            if self._clap.feed(rms, self._t):
                fired = "clap"

        if self._wake is not None:
            self._pending = np.concatenate([self._pending, samples])
            while len(self._pending) >= WAKE_FRAME:
                frame, self._pending = (
                    self._pending[:WAKE_FRAME],
                    self._pending[WAKE_FRAME:],
                )
                if self._t < self._quiet_until:
                    continue
                if self._wake.score(frame) >= self._wake.threshold:
                    self._wake.reset()
                    self._quiet_until = self._t + self._cooldown
                    fired = fired or "jarvis"
        return fired


def wait_for_trigger(
    listener: TriggerListener,
    *,
    sample_rate: int = SAMPLE_RATE,
    should_stop: Callable[[], bool] = lambda: False,
    stream_factory: Optional[Callable[[], Any]] = None,
) -> Optional[str]:
    """Block on the default microphone until a trigger fires.

    Returns the trigger name, or ``None`` if ``should_stop`` asked to bail out.
    """
    if stream_factory is None:
        try:
            import sounddevice as sd
        except ImportError as exc:
            raise RuntimeError(
                "sounddevice is required to listen. "
                "Install with: pip install 'OpenJarvis[speech]'"
            ) from exc

        def stream_factory() -> Any:
            return sd.RawInputStream(
                samplerate=sample_rate, channels=1, dtype="int16", blocksize=BLOCK
            )

    listener.reset()
    with stream_factory() as stream:
        while not should_stop():
            data, _overflowed = stream.read(BLOCK)
            fired = listener.feed(bytes(data))
            if fired:
                return fired
    return None


__all__ = [
    "BLOCK",
    "WAKE_FRAME",
    "WAKE_MODES",
    "TriggerListener",
    "WakeWordDetector",
    "normalize_mode",
    "wait_for_trigger",
]
