"""Double-clap detector on synthetic RMS envelopes (32 ms chunks)."""

from openjarvis.speech.clap import ClapDetector

DT = 0.032


def _run(det: ClapDetector, envelope: list[float]) -> list[int]:
    return [i for i, rms in enumerate(envelope) if det.feed(rms, (i + 1) * DT)]


def _quiet(n: int) -> list[float]:
    return [150.0] * n


CLAP = [9000.0, 9000.0]  # ~64 ms burst


def test_two_claps_trigger_once() -> None:
    env = _quiet(30) + CLAP + _quiet(10) + CLAP + _quiet(30)
    assert len(_run(ClapDetector(), env)) == 1


def test_single_clap_does_not_trigger() -> None:
    assert _run(ClapDetector(), _quiet(30) + CLAP + _quiet(60)) == []


def test_claps_too_far_apart_do_not_trigger() -> None:
    env = _quiet(30) + CLAP + _quiet(60) + CLAP + _quiet(30)
    assert _run(ClapDetector(), env) == []


def test_sustained_noise_is_not_a_clap() -> None:
    env = _quiet(30) + [9000.0] * 20 + _quiet(5) + [9000.0] * 20 + _quiet(30)
    assert _run(ClapDetector(), env) == []


def test_quiet_taps_below_sensitivity_ignored() -> None:
    tap = [1500.0, 1500.0]
    env = _quiet(30) + tap + _quiet(10) + tap + _quiet(30)
    assert _run(ClapDetector(), env) == []
    assert len(_run(ClapDetector(min_level=1000), env)) == 1


def test_cooldown_blocks_immediate_retrigger() -> None:
    double = CLAP + _quiet(10) + CLAP
    env = _quiet(30) + double + _quiet(5) + double + _quiet(30)
    assert len(_run(ClapDetector(), env)) == 1
