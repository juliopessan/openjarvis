"""``jarvis listen`` -- hands-free voice assistant.

Say "Jarvis" (or clap twice) and talk. After each answer Jarvis keeps listening
for a follow-up, so a conversation needs only one wake-up; it goes back to
standby after a pause, or when you say goodbye.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Callable, Optional

import click
from rich.console import Console

from openjarvis.core.types import Message, Role

# Tools a spoken request may use. mac_control is a fixed list of safe actions;
# there is no free-form shell here.
DEFAULT_VOICE_TOOLS = ["mac_control", "web_search", "digest_collect", "think"]
DEFAULT_VOICE_AGENT = "orchestrator"

# How long to wait for the first request after the greeting.
FIRST_REQUEST_WAIT = 6.0
# Remembered messages (user + assistant) passed back for follow-ups.
MAX_HISTORY_MESSAGES = 12

# UI strings per language; picked from ``[speech] language`` (English default).
_STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "greeting": "Yes, {name}?",
        "greeting_bare": "Yes?",
        "ready_jarvis": 'Jarvis is listening — say "Jarvis".',
        "ready_clap": "Jarvis is listening — clap twice to wake.",
        "ready_both": 'Jarvis is listening — say "Jarvis" or clap twice.',
        "loading": "Loading voice…",
        "awake": "Awake",
        "standby": "Back to standby.",
        "stopped": "Jarvis stopped listening.",
        "error": "Sorry, I couldn't reach my model.",
        "goodbye": "Goodbye.",
        "style": (
            "You are Jarvis, a voice assistant. Your answer will be spoken "
            "aloud: reply in English in at most three short sentences, plain "
            "text, no lists or markdown. Use your tools when the request needs "
            "them, and briefly say what you did."
        ),
    },
    "pt": {
        "greeting": "Pois não, {name}?",
        "greeting_bare": "Pois não?",
        "ready_jarvis": 'Jarvis ouvindo — diga "Jarvis".',
        "ready_clap": "Jarvis ouvindo — bata duas palmas para acordar.",
        "ready_both": 'Jarvis ouvindo — diga "Jarvis" ou bata duas palmas.',
        "loading": "Carregando a voz…",
        "awake": "Acordado",
        "standby": "De volta à espera.",
        "stopped": "Jarvis parou de ouvir.",
        "error": "Desculpe, não consegui falar com o modelo.",
        "goodbye": "Até logo.",
        "style": (
            "Você é o Jarvis, um assistente de voz. Sua resposta será falada "
            "em voz alta: responda em português do Brasil, em no máximo três "
            "frases curtas, texto simples, sem listas nem markdown. Use suas "
            "ferramentas quando o pedido exigir e diga brevemente o que fez."
        ),
    },
}

# Phrases that end a conversation (matched on accent-free lowercase words).
_GOODBYE_PHRASES = (
    "tchau",
    "ate logo",
    "obrigado",
    "obrigada",
    "valeu",
    "so isso",
    "e so isso",
    "pode parar",
    "pode ir",
    "encerrar",
    "goodbye",
    "bye",
    "thanks",
    "thank you",
    "that is all",
    "thats all",
    "stop",
)
# Words that may accompany a goodbye without being a new request.
_FILLER_WORDS = frozenset(
    "jarvis por favor muito tudo entao ok okay a o e pra voce mesmo vlw "
    "much very you so well".split()
)


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


def _words(text: str) -> list[str]:
    """Accent-free lowercase words, punctuation removed."""
    folded = unicodedata.normalize("NFD", text.lower())
    folded = "".join(ch for ch in folded if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9\s]", " ", folded.replace("'", "")).split()


def is_goodbye(text: str) -> bool:
    """True when ``text`` only says goodbye, with no new request mixed in."""
    words = _words(text)
    if not words or len(words) > 8:
        return False
    remaining = " ".join(words)
    matched = False
    for phrase in sorted(_GOODBYE_PHRASES, key=len, reverse=True):
        pattern = rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])"
        if re.search(pattern, remaining):
            matched = True
            remaining = re.sub(pattern, " ", remaining)
    return matched and all(w in _FILLER_WORDS for w in remaining.split())


def run_conversation(
    *,
    greeting: str,
    goodbye: str,
    ask: Callable[[str, list[Message]], str],
    record: Callable[[float], Any],
    speak: Callable[[str], None],
    exit_signal: object,
    follow_up_seconds: float,
    console: Any = None,
) -> bool:
    """Run one wake-up: greet, then answer requests until a pause or goodbye.

    ``record(wait_seconds)`` returns the transcript, ``None`` for silence, or
    ``exit_signal`` when listening cannot continue. Returns ``False`` when the
    whole program should stop, ``True`` to go back to standby.
    """
    history: list[Message] = []
    speak(greeting)
    wait = FIRST_REQUEST_WAIT
    while True:
        heard = record(wait)
        if heard is exit_signal:
            return False
        if not heard:
            return True
        text = str(heard)
        if is_goodbye(text):
            speak(goodbye)
            return True

        answer = ask(text, history)
        if console is not None:
            console.print(f"[bold]Jarvis:[/bold] {answer}")
        speak(answer)

        history.append(Message(role=Role.USER, content=text))
        history.append(Message(role=Role.ASSISTANT, content=answer))
        del history[:-MAX_HISTORY_MESSAGES]

        if follow_up_seconds <= 0:
            return True
        wait = follow_up_seconds


def _build_triggers(mode: str, sensitivity: float, threshold: float, console: Any):
    """Create the trigger listener, degrading ``both`` to claps if needed."""
    from openjarvis.speech.clap import ClapDetector
    from openjarvis.speech.trigger import TriggerListener, WakeWordDetector

    wake: Optional[WakeWordDetector] = None
    if mode in ("jarvis", "both"):
        try:
            wake = WakeWordDetector(threshold=threshold)
        except RuntimeError as exc:
            if mode == "jarvis":
                raise click.ClickException(str(exc)) from exc
            console.print(f"[yellow]{exc} Using claps only.[/yellow]")
            mode = "clap"
    return mode, TriggerListener(
        mode, wake=wake, clap=ClapDetector(min_level=sensitivity)
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
    "--wake",
    "wake_mode",
    type=click.Choice(["jarvis", "clap", "both"], case_sensitive=False),
    default=None,
    help='What wakes Jarvis: the word "Jarvis", a double clap, or both. '
    "Defaults to [speech] wake in the config.",
)
@click.option(
    "--sensitivity",
    type=click.FloatRange(500, 20000),
    default=3000.0,
    show_default=True,
    help="Minimum clap loudness (RMS). Lower = more sensitive.",
)
@click.option(
    "--agent",
    "agent_name",
    default=None,
    help=f"Agent that answers (default: {DEFAULT_VOICE_AGENT}).",
)
@click.option(
    "--tools",
    "tool_names",
    default=None,
    help="Comma-separated tools Jarvis may use "
    f"(default: {','.join(DEFAULT_VOICE_TOOLS)}).",
)
@click.option("--once", is_flag=True, help="Handle one conversation, then exit.")
def listen(
    wake_mode: str | None,
    sensitivity: float,
    agent_name: str | None,
    tool_names: str | None,
    once: bool,
) -> None:
    """Wait for "Jarvis" or two claps, then hold a spoken conversation.

    Replies follow ``[speech] language`` (e.g. "pt" for Portuguese).
    Press Ctrl-C to stop.
    """
    from openjarvis.cli._voice_chat import (
        VOICE_EXIT,
        VoiceSession,
        record_voice,
        speak_streaming,
    )
    from openjarvis.core.config import load_config
    from openjarvis.speech.trigger import normalize_mode, wait_for_trigger

    console = Console()
    config = load_config()
    speech = config.speech
    text = _strings(config)
    session = VoiceSession(config)
    mode, triggers = _build_triggers(
        normalize_mode(wake_mode or getattr(speech, "wake", "clap")),
        sensitivity,
        float(getattr(speech, "wake_threshold", 0.5)),
        console,
    )
    follow_up = float(getattr(speech, "follow_up_seconds", 8.0))
    tools = (
        [t.strip() for t in tool_names.split(",") if t.strip()]
        if tool_names is not None
        else list(DEFAULT_VOICE_TOOLS)
    )
    agent = agent_name or (DEFAULT_VOICE_AGENT if tools else None)
    jarvis = None

    def ask(heard: str, history: list[Message]) -> str:
        nonlocal jarvis
        if jarvis is None:
            from openjarvis.sdk import Jarvis

            jarvis = Jarvis(config=config)
        try:
            return jarvis.ask(
                f"{text['style']}\n\n{heard}",
                agent=agent,
                tools=tools or None,
                history=list(history),
            )
        except Exception as exc:  # engine down, model missing, ...
            console.print(f"[red]Jarvis error: {exc}[/red]")
            return text["error"]

    console.print(f"[dim]{text['loading']}[/dim]")
    _warm_up_voice(session, console)
    console.print(f"[cyan]{text['ready_' + mode]}[/cyan]")
    try:
        while True:
            try:
                fired = wait_for_trigger(triggers)
            except RuntimeError as exc:
                raise click.ClickException(str(exc)) from exc
            if fired is None:
                break

            console.print(f"[bold green]{text['awake']} ({fired})[/bold green]")
            keep_going = run_conversation(
                greeting=_greeting(config),
                goodbye=text["goodbye"],
                ask=ask,
                record=lambda wait: record_voice(console, session, wait_seconds=wait),
                speak=lambda line: speak_streaming(line, console, session),
                exit_signal=VOICE_EXIT,
                follow_up_seconds=follow_up,
                console=console,
            )
            if once or not keep_going:
                break
            console.print(f"[dim]{text['standby']}[/dim]")
    except KeyboardInterrupt:
        pass
    finally:
        if jarvis is not None:
            jarvis.close()
    console.print(f"[dim]{text['stopped']}[/dim]")
