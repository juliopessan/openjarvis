"""Preset installation must preserve safe local server defaults (#770)."""

from pathlib import Path
from unittest import mock

from click.testing import CliRunner

from openjarvis.cli import cli
from openjarvis.core.config import load_config
from openjarvis.server.auth_middleware import check_bind_safety


def test_chat_simple_preset_can_serve_without_an_api_key(tmp_path: Path) -> None:
    config_dir = tmp_path / ".openjarvis"
    config_path = config_dir / "config.toml"
    with (
        mock.patch("openjarvis.cli.init_cmd.DEFAULT_CONFIG_DIR", config_dir),
        mock.patch("openjarvis.cli.init_cmd.DEFAULT_CONFIG_PATH", config_path),
    ):
        result = CliRunner().invoke(
            cli,
            ["init", "--preset", "chat-simple", "--no-download", "--no-scan"],
        )

    assert result.exit_code == 0, result.output
    config = load_config(config_path)
    assert config.server.host == "127.0.0.1"
    check_bind_safety(config.server.host, api_key="")


def test_daily_ops_mac_preset_loads(tmp_path: Path) -> None:
    config_dir = tmp_path / ".openjarvis"
    config_path = config_dir / "config.toml"
    with (
        mock.patch("openjarvis.cli.init_cmd.DEFAULT_CONFIG_DIR", config_dir),
        mock.patch("openjarvis.cli.init_cmd.DEFAULT_CONFIG_PATH", config_path),
    ):
        result = CliRunner().invoke(
            cli,
            ["init", "--preset", "daily-ops-mac", "--no-download", "--no-scan"],
        )

    assert result.exit_code == 0, result.output
    config = load_config(config_path)
    assert config.engine.default == "ollama"
    assert config.deep_research.engine == "cloud"
    assert config.digest.enabled is True
    assert config.digest.timezone == "America/Sao_Paulo"
    assert config.digest.tts_backend == "kokoro"
    assert config.speech.tts_backend == "kokoro"
    assert config.speech.voice_id == "bm_george"
    check_bind_safety(config.server.host, api_key="")
