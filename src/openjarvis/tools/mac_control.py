"""macOS control tool: a fixed, safe set of actions for voice commands.

Deliberately not a shell. Each action builds its own argument list from
validated parameters, runs it without a shell, and never interpolates
user-provided text into an AppleScript or command line. Anything outside the
action list (running arbitrary commands, quitting apps, shutting down) is
simply not available through this tool.
"""

from __future__ import annotations

import re
import subprocess
import sys
from typing import Any, Callable, List, Optional
from urllib.parse import urlparse

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec

ACTIONS = (
    "open_app",
    "open_url",
    "set_volume",
    "change_volume",
    "mute",
    "unmute",
    "media",
    "dark_mode",
    "sleep_display",
    "notify",
)

_MEDIA_APPS = ("Music", "Spotify")
_MEDIA_COMMANDS = {
    "play_pause": "playpause",
    "next": "next track",
    "previous": "previous track",
}
_DARK_MODE = {
    "on": "set dark mode to true",
    "off": "set dark mode to false",
    "toggle": "set dark mode to not dark mode",
}

# First character must be alphanumeric so a name can never look like a flag.
_APP_NAME = re.compile(r"^[^\W_][\w .&'+()-]{0,63}$")
_MAX_URL = 2048
_COMMAND_TIMEOUT = 10

Runner = Callable[..., "subprocess.CompletedProcess[str]"]


class MacControlError(ValueError):
    """Raised when parameters are invalid; the message is safe to speak."""


def _clamp_int(value: Any, low: int, high: int, name: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise MacControlError(f"{name} must be a whole number.") from None
    return max(low, min(high, number))


def _osascript(*lines: str, args: Optional[List[str]] = None) -> List[str]:
    """Build an ``osascript`` command; ``args`` reach the script as ``argv``."""
    cmd = ["osascript"]
    for line in lines:
        cmd += ["-e", line]
    if args:
        cmd += ["--", *args]
    return cmd


def build_command(action: str, params: dict[str, Any]) -> List[str]:
    """Validate ``params`` and return the argument list for ``action``."""
    if action == "open_app":
        name = str(params.get("name", "")).strip()
        if not _APP_NAME.match(name):
            raise MacControlError("That is not a valid application name.")
        return ["open", "-a", name]

    if action == "open_url":
        url = str(params.get("url", "")).strip()
        parsed = urlparse(url)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.netloc
            or len(url) > _MAX_URL
            or any(ch.isspace() for ch in url)
        ):
            raise MacControlError("Only http and https links can be opened.")
        return ["open", url]

    if action == "set_volume":
        level = _clamp_int(params.get("level"), 0, 100, "level")
        return _osascript(f"set volume output volume {level}")

    if action == "change_volume":
        delta = _clamp_int(params.get("delta", 10), -100, 100, "delta")
        return _osascript(
            "set current to output volume of (get volume settings)",
            f"set volume output volume (current + ({delta}))",
        )

    if action == "mute":
        return _osascript("set volume with output muted")

    if action == "unmute":
        return _osascript("set volume without output muted")

    if action == "media":
        app = params.get("app", "Music")
        command = params.get("command", "play_pause")
        if app not in _MEDIA_APPS:
            raise MacControlError("Media control supports Music and Spotify.")
        if command not in _MEDIA_COMMANDS:
            raise MacControlError("Use play_pause, next or previous.")
        return _osascript(f'tell application "{app}" to {_MEDIA_COMMANDS[command]}')

    if action == "dark_mode":
        mode = params.get("mode", "toggle")
        if mode not in _DARK_MODE:
            raise MacControlError("Use on, off or toggle.")
        return _osascript(
            'tell application "System Events"',
            f"tell appearance preferences to {_DARK_MODE[mode]}",
            "end tell",
        )

    if action == "sleep_display":
        return ["pmset", "displaysleepnow"]

    if action == "notify":
        title = str(params.get("title", "Jarvis")).strip()[:120] or "Jarvis"
        message = str(params.get("message", "")).strip()[:240]
        if not message:
            raise MacControlError("A notification needs a message.")
        # Values travel as argv, never inside the script text.
        return _osascript(
            "on run argv",
            "display notification (item 2 of argv) with title (item 1 of argv)",
            "end run",
            args=[title, message],
        )

    raise MacControlError(f"Unknown action. Available: {', '.join(ACTIONS)}.")


_SUCCESS = {
    "open_app": "Opened the app.",
    "open_url": "Opened the link.",
    "set_volume": "Volume set.",
    "change_volume": "Volume changed.",
    "mute": "Muted.",
    "unmute": "Unmuted.",
    "media": "Done.",
    "dark_mode": "Appearance changed.",
    "sleep_display": "Display put to sleep.",
    "notify": "Notification shown.",
}


@ToolRegistry.register("mac_control")
class MacControlTool(BaseTool):
    """Open apps and links, adjust volume, control music, and more on macOS."""

    tool_id = "mac_control"

    def __init__(self, runner: Optional[Runner] = None) -> None:
        self._run: Runner = runner or subprocess.run

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="mac_control",
            description=(
                "Control this Mac with one safe action at a time: open an "
                "application or an http(s) link, set or change the volume, "
                "mute, play/pause/skip music (Music or Spotify), switch dark "
                "mode, put the display to sleep, or show a notification."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": list(ACTIONS),
                        "description": "What to do.",
                    },
                    "name": {
                        "type": "string",
                        "description": "open_app: application name, e.g. Safari.",
                    },
                    "url": {
                        "type": "string",
                        "description": "open_url: an http or https link.",
                    },
                    "level": {
                        "type": "integer",
                        "description": "set_volume: 0 (silent) to 100 (maximum).",
                    },
                    "delta": {
                        "type": "integer",
                        "description": "change_volume: points to add; negative lowers.",
                    },
                    "command": {
                        "type": "string",
                        "enum": list(_MEDIA_COMMANDS),
                        "description": "media: play_pause, next or previous.",
                    },
                    "app": {
                        "type": "string",
                        "enum": list(_MEDIA_APPS),
                        "description": "media: Music (default) or Spotify.",
                    },
                    "mode": {
                        "type": "string",
                        "enum": list(_DARK_MODE),
                        "description": "dark_mode: on, off or toggle.",
                    },
                    "title": {
                        "type": "string",
                        "description": "notify: notification title.",
                    },
                    "message": {
                        "type": "string",
                        "description": "notify: notification text.",
                    },
                },
                "required": ["action"],
            },
            category="system",
            timeout_seconds=15.0,
            required_capabilities=["tool:invoke"],
        )

    def execute(self, **params: Any) -> ToolResult:
        if sys.platform != "darwin":
            return ToolResult(
                tool_name="mac_control",
                content="mac_control only works on macOS.",
                success=False,
            )

        action = str(params.pop("action", ""))
        try:
            command = build_command(action, params)
        except MacControlError as exc:
            return ToolResult(tool_name="mac_control", content=str(exc), success=False)

        try:
            done = self._run(
                command,
                capture_output=True,
                text=True,
                timeout=_COMMAND_TIMEOUT,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                tool_name="mac_control",
                content="The action timed out.",
                success=False,
            )
        except OSError as exc:
            return ToolResult(
                tool_name="mac_control",
                content=f"Could not run the action: {exc}",
                success=False,
            )

        if done.returncode != 0:
            detail = (done.stderr or "").strip()[:300] or "unknown error"
            return ToolResult(
                tool_name="mac_control",
                content=f"The action failed: {detail}",
                success=False,
            )
        return ToolResult(
            tool_name="mac_control",
            content=_SUCCESS[action],
            success=True,
            metadata={"action": action},
        )


__all__ = ["ACTIONS", "MacControlError", "MacControlTool", "build_command"]
