"""mac_control builds validated argument lists and never touches a shell."""

from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest

import openjarvis.tools.mac_control as mac_control

# Other suites reload tool modules, which rebinds the classes inside the module.
# Looking names up at call time keeps these tests valid after such a reload.


def build_command(*args, **kwargs):
    return mac_control.build_command(*args, **kwargs)


def MacControlTool(*args, **kwargs):  # noqa: N802 - mirrors the class name
    return mac_control.MacControlTool(*args, **kwargs)


def _tool(returncode: int = 0, stderr: str = "", seen: list | None = None):
    def runner(cmd, **kwargs):
        if seen is not None:
            seen.append((cmd, kwargs))
        return SimpleNamespace(returncode=returncode, stderr=stderr, stdout="")

    return MacControlTool(runner=runner)


@pytest.fixture(autouse=True)
def on_mac(monkeypatch):
    monkeypatch.setattr("openjarvis.tools.mac_control.sys.platform", "darwin")


def test_open_app_builds_an_open_command() -> None:
    assert build_command("open_app", {"name": "Visual Studio Code"}) == [
        "open",
        "-a",
        "Visual Studio Code",
    ]


@pytest.mark.parametrize(
    "name",
    ["", "-a", "--help", "../etc/passwd", "Safari; rm -rf /", "a" * 80, "$(whoami)"],
)
def test_open_app_rejects_flags_paths_and_shell_syntax(name: str) -> None:
    with pytest.raises(mac_control.MacControlError):
        build_command("open_app", {"name": name})


def test_open_url_accepts_only_http_and_https() -> None:
    assert build_command("open_url", {"url": "https://example.com/a?b=1"}) == [
        "open",
        "https://example.com/a?b=1",
    ]
    for bad in (
        "file:///etc/passwd",
        "javascript:alert(1)",
        "ssh://host",
        "example.com",
        "https://",
        "https://a.com/ b",
        "https://a.com/" + "x" * 3000,
    ):
        with pytest.raises(mac_control.MacControlError):
            build_command("open_url", {"url": bad})


def test_volume_is_clamped_and_must_be_numeric() -> None:
    assert build_command("set_volume", {"level": 250})[-1] == (
        "set volume output volume 100"
    )
    assert build_command("set_volume", {"level": -5})[-1] == (
        "set volume output volume 0"
    )
    with pytest.raises(mac_control.MacControlError):
        build_command("set_volume", {"level": "loud; do shell script"})


def test_change_volume_embeds_only_an_integer() -> None:
    cmd = build_command("change_volume", {"delta": "-15"})
    assert "(-15)" in cmd[-1]
    with pytest.raises(mac_control.MacControlError):
        build_command("change_volume", {"delta": "1) & (do shell script"})


def test_media_is_restricted_to_known_apps_and_commands() -> None:
    cmd = build_command("media", {"app": "Spotify", "command": "next"})
    assert cmd[-1] == 'tell application "Spotify" to next track'
    for params in (
        {"app": "Terminal", "command": "next"},
        {"app": "Music", "command": 'x" & (do shell script "id")'},
    ):
        with pytest.raises(mac_control.MacControlError):
            build_command("media", params)


def test_dark_mode_modes_are_whitelisted() -> None:
    assert "not dark mode" in " ".join(build_command("dark_mode", {"mode": "toggle"}))
    with pytest.raises(mac_control.MacControlError):
        build_command("dark_mode", {"mode": "purple"})


def test_notify_passes_text_as_arguments_not_script_text() -> None:
    evil = 'hi" & (do shell script "id") & "'
    cmd = build_command("notify", {"title": "Aviso", "message": evil})
    script = " ".join(cmd[: cmd.index("--")])
    assert "do shell script" not in script
    assert cmd[cmd.index("--") + 1 :] == ["Aviso", evil]
    with pytest.raises(mac_control.MacControlError):
        build_command("notify", {"message": "   "})


def test_unknown_actions_are_refused() -> None:
    with pytest.raises(mac_control.MacControlError):
        build_command("shell", {"command": "rm -rf /"})
    assert "shell" not in mac_control.ACTIONS


def test_execute_runs_without_a_shell_and_reports_success() -> None:
    seen: list = []
    result = _tool(seen=seen).execute(action="open_app", name="Safari")
    assert result.success
    command, kwargs = seen[0]
    assert command == ["open", "-a", "Safari"]
    assert "shell" not in kwargs or kwargs["shell"] is False
    assert kwargs["timeout"] > 0


def test_execute_reports_command_failures_and_validation_errors() -> None:
    failed = _tool(returncode=1, stderr="Unable to find application").execute(
        action="open_app", name="Nope"
    )
    assert not failed.success and "Unable to find application" in failed.content
    invalid = _tool().execute(action="open_app", name="--help")
    assert not invalid.success


def test_execute_handles_timeouts() -> None:
    def runner(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, 10)

    result = MacControlTool(runner=runner).execute(action="mute")
    assert not result.success and "timed out" in result.content


def test_other_platforms_get_a_clear_refusal(monkeypatch) -> None:
    monkeypatch.setattr("openjarvis.tools.mac_control.sys.platform", "linux")
    seen: list = []
    result = _tool(seen=seen).execute(action="mute")
    assert not result.success and "macOS" in result.content
    assert seen == []


def test_spec_exposes_every_action_and_is_registered() -> None:
    import importlib

    import openjarvis.tools.mac_control as module
    from openjarvis.core.registry import ToolRegistry
    from openjarvis.security.capabilities import DEFAULT_TOOL_CAPABILITIES

    module = importlib.reload(module)  # the suite clears registries per test
    assert ToolRegistry.get("mac_control") is module.MacControlTool

    spec = module.MacControlTool().spec
    assert spec.parameters["properties"]["action"]["enum"] == list(mac_control.ACTIONS)
    assert spec.required_capabilities == ["tool:invoke"]
    assert DEFAULT_TOOL_CAPABILITIES["mac_control"] == ["tool:invoke"]
