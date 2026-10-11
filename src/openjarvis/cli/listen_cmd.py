"""``jarvis listen`` -- hands-free voice assistant woken by a double clap."""

from __future__ import annotations

from typing import Any

import click
from rich.console import Console


def _greeting(config: Any) -> str:
    honorific = (
        getattr(getattr(config, "digest", None), "honorific", "") or ""
    ).strip()
    return f"Yes, {honorific}?" if honorific else "Yes?"


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
    Press Ctrl-C to stop.
    """
    from openjarvis.cli._voice_chat import VOICE_EXIT, VoiceSession, record_voice, speak
    from openjarvis.core.config import load_config
    from openjarvis.speech.clap import ClapDetector, wait_for_double_clap

    console = Console()
    config = load_config()
    session = VoiceSession(config)
    detector = ClapDetector(min_level=sensitivity)
    jarvis = None

    console.print("[cyan]Jarvis is listening — clap twice to wake.[/cyan]")
    try:
        while True:
            try:
                if not wait_for_double_clap(detector):
                    break
            except RuntimeError as exc:
                raise click.ClickException(str(exc)) from exc

            console.print("[bold green]👏👏 Awake[/bold green]")
            speak(_greeting(config), console, session)
            heard = record_voice(console, session)
            if heard is VOICE_EXIT:
                break
            if heard:
                if jarvis is None:
                    from openjarvis.sdk import Jarvis

                    jarvis = Jarvis(config=config)
                try:
                    answer = jarvis.ask(str(heard), agent=agent_name)
                except Exception as exc:  # engine down, model missing, ...
                    console.print(f"[red]Jarvis error: {exc}[/red]")
                    answer = "Sorry, I couldn't reach my model."
                console.print(f"[bold]Jarvis:[/bold] {answer}")
                speak(answer, console, session)
            if once:
                break
            console.print("[dim]Back to standby — clap twice.[/dim]")
    except KeyboardInterrupt:
        pass
    finally:
        if jarvis is not None:
            jarvis.close()
    console.print("[dim]Jarvis stopped listening.[/dim]")
