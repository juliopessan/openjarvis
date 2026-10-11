"""Double-clap wake trigger.

A clap is a sharp transient: loudness jumps well above the running noise
floor and falls back within a fraction of a second. Two claps inside a short
window wake the assistant. Detection is pure arithmetic over per-chunk RMS
values so it is testable without a microphone.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

_SAMPLE_RATE = 16000
_CHUNK = 512  # 32 ms at 16 kHz — short enough to resolve a clap's edge


@dataclass
class ClapDetector:
    """Feed ``(rms, t)`` per audio chunk; ``feed`` returns True on a double clap."""

    min_level: float = 3000.0  # absolute RMS a clap must reach (16-bit PCM)
    rise_ratio: float = 6.0  # clap must exceed noise floor by this factor
    max_clap_seconds: float = 0.15  # longer than this is speech/music, not a clap
    min_gap: float = 0.15  # seconds between the two claps
    max_gap: float = 0.9
    cooldown: float = 1.5  # ignore input after a trigger

    _floor: float = field(default=200.0, init=False)
    _onset: Optional[float] = field(default=None, init=False)
    _last_clap: Optional[float] = field(default=None, init=False)
    _quiet_until: float = field(default=0.0, init=False)

    def feed(self, rms: float, t: float) -> bool:
        if t < self._quiet_until:
            return False

        loud = rms >= self.min_level and rms >= self._floor * self.rise_ratio
        if loud:
            if self._onset is None:
                self._onset = t
            return False

        if self._onset is None:
            # Track ambient noise slowly so a noisy room raises the bar.
            self._floor = 0.95 * self._floor + 0.05 * max(rms, 50.0)
            return False

        duration = t - self._onset
        onset, self._onset = self._onset, None
        if duration > self.max_clap_seconds:
            self._last_clap = None
            return False

        last, self._last_clap = self._last_clap, onset
        if last is not None and self.min_gap <= onset - last <= self.max_gap:
            self._last_clap = None
            self._quiet_until = t + self.cooldown
            return True
        return False


def wait_for_double_clap(
    detector: Optional[ClapDetector] = None,
    *,
    sample_rate: int = _SAMPLE_RATE,
    should_stop: Callable[[], bool] = lambda: False,
) -> bool:
    """Block on the default microphone until two claps are heard.

    Returns False if ``should_stop`` asked to bail out first.
    """
    try:
        import sounddevice as sd
    except ImportError:
        raise RuntimeError(
            "sounddevice is required for clap detection. "
            "Install with: pip install 'OpenJarvis[speech]'"
        )

    from openjarvis.speech.voice_io import _rms

    det = detector or ClapDetector()
    chunk_seconds = _CHUNK / sample_rate
    t = 0.0
    with sd.RawInputStream(
        samplerate=sample_rate, channels=1, dtype="int16", blocksize=_CHUNK
    ) as stream:
        while not should_stop():
            data, _overflowed = stream.read(_CHUNK)
            t += chunk_seconds
            if det.feed(_rms(bytes(data)), t):
                return True
    return False
