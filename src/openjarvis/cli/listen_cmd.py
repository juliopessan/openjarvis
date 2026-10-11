"""``jarvis listen`` -- hands-free voice assistant woken by a double clap."""

from __future__ import annotations

from typing import Any

import click
from rich.console import Console

# UI strings per language; picked from ``[speech] language`` (English default).
_STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "greeting": "Yes, {name}?",
        "greeting_bare": "Yes?",
        "ready": "Jarvis is listening — clap twice to wake.",
        "loading": "Loading voice…",
        "awake": "👏👏 Awake",
        "standby": "Back to standby — clap twice.",
        "stopped": "Jarvis stopped listening.",
        "error": "Sorry, I couldn't reach my model.",
        "style": (
            "You are Jarvis, a voice assistant. Your answer will be spoken "
            "aloud: reply in English in at most three short sentences, plain "
            "text, no lists or markdown."
        ),
    },
    "pt": {
        "greeting": "Pois não, {name}?",
        "greeting_bare": "Pois não?",
        "ready": "Jarvis ouvindo — bata duas palmas para acordar.",
        "loading": "Carregando a voz…",
        "awake": "👏👏 Acordado",
        "standby": "De volta à espera — bata duas palmas.",
        "stopped": "Jarvis parou de ouvir.",
        "error": "Desculpe, não consegui falar com o modelo.",
        "style": (
            "Você é o Jarvis, um assistente de voz. Sua resposta será falada "
            "em voz alta: responda em português do Brasil, em no máximo três "
            "frases curtas, texto simples, sem listas nem markdown."
        ),
    },
}


def _strings(config: Any) -> dict[str, str]:
    language = (getattr(getattr(config, "speech", None), "language", "") or "").lower()
    return _STRINGS.get(language[:2], _STRINGS["en"])


def _greeting(config: Any) -> str:
    text = _strings(config)
    honorific = (
        getattr(getattr(config, "digest", None), "honorific", "") or ""
    ).strip()
    return (
        text["greeting"].format(name=honorific) if honorific else text["greeting_bare"]
    )


def _warm_up_voice(session: Any, console: Any) -> None:
    """Load the TTS model now so the first wake answers immediately."""
    backend = session.get_tts_backend()
    if backend is None:
        return
    try:
        voice_id, speed = session.voice_for_backend(backend, console)
        kwargs: dict[str, Any] = {"output_format": "wav", "speed": speed}
        if voice_id:
            kwargs["voice_id"] = voice_id
        backend.synthesize("ok", **kwargs)
    except Exception:  # speak() reports and falls back on first real use
        pass


@click.command()
@click.option(
    "--sensitivity",
    type=click.FloatRange(500, 20000),
    default=3000.0,
    show_default=True,
    help="Minimum clap loudness (RMS). Lower = more sensitive.",
)
@click.option("--agent", "agent_name", default=None, help="Agent that answers.")
@click.option("--once", is_flag=True, help="Handle one request, then exit.")
def listen(sensitivity: float, agent_name: str | None, once: bool) -> None:
    """Wait for two claps, then listen and answer out loud.

    Clap twice, wait for Jarvis to answer, then speak your request.
    Replies follow ``[speech] language`` (e.g. "pt" for Portuguese).
    Press Ctrl-C to stop.
    """
    from openjarvis.cli._voice_chat import VOICE_EXIT, VoiceSession, record_voice, speak
    from openjarvis.core.config import load_config
    from openjarvis.speech.clap import ClapDetector, wait_for_double_clap

    console = Console()
    config = load_config()
    text = _strings(config)
    session = VoiceSession(config)
    detector = ClapDetector(min_level=sensitivity)
    jarvis = None

    console.print(f"[dim]{text['loading']}[/dim]")
    _warm_up_voice(session, console)
    console.print(f"[cyan]{text['ready']}[/cyan]")
    try:
        while True:
            try:
                if not wait_for_double_clap(detector):
                    break
            except RuntimeError as exc:
                raise click.ClickException(str(exc)) from exc

            console.print(f"[bold green]{text['awake']}[/bold green]")
            speak(_greeting(config), console, session)
            heard = record_voice(console, session)
            if heard is VOICE_EXIT:
                break
            if heard:
                if jarvis is None:
                    from openjarvis.sdk import Jarvis

                    jarvis = Jarvis(config=config)
                try:
                    answer = jarvis.ask(f"{text['style']}\n\n{heard}", agent=agent_name)
                except Exception as exc:  # engine down, model missing, ...
                    console.print(f"[red]Jarvis error: {exc}[/red]")
                    answer = text["error"]
                console.print(f"[bold]Jarvis:[/bold] {answer}")
                speak(answer, console, session)
            if once:
                break
            console.print(f"[dim]{text['standby']}[/dim]")
    except KeyboardInterrupt:
        pass
    finally:
        if jarvis is not None:
            jarvis.close()
    console.print(f"[dim]{text['stopped']}[/dim]")
