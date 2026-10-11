"""``jarvis listen`` wakes on a double clap, answers, and speaks."""

from unittest import mock

from click.testing import CliRunner

from openjarvis.cli import cli
from openjarvis.core.config import JarvisConfig


def test_listen_once_answers_out_loud() -> None:
    config = JarvisConfig()
    config.digest.honorific = "Julio"
    spoken: list[str] = []
    fake_jarvis = mock.MagicMock()
    fake_jarvis.ask.return_value = "All systems nominal."

    with (
        mock.patch("openjarvis.core.config.load_config", return_value=config),
        mock.patch("openjarvis.speech.clap.wait_for_double_clap", return_value=True),
        mock.patch(
            "openjarvis.cli._voice_chat.record_voice", return_value="status report"
        ),
        mock.patch(
            "openjarvis.cli._voice_chat.speak",
            side_effect=lambda text, *a, **k: spoken.append(text),
        ),
        mock.patch("openjarvis.sdk.Jarvis", return_value=fake_jarvis),
        mock.patch("openjarvis.cli.listen_cmd._warm_up_voice"),
    ):
        result = CliRunner().invoke(cli, ["listen", "--once"])

    assert result.exit_code == 0, result.output
    assert spoken == ["Yes, Julio?", "All systems nominal."]
    fake_jarvis.ask.assert_called_once()
    assert fake_jarvis.ask.call_args.args[0].endswith("status report")
    fake_jarvis.close.assert_called_once()


def test_listen_speaks_portuguese_when_configured() -> None:
    config = JarvisConfig()
    config.digest.honorific = "Julio"
    config.speech.language = "pt"
    spoken: list[str] = []
    fake_jarvis = mock.MagicMock()
    fake_jarvis.ask.return_value = "Tudo certo."

    with (
        mock.patch("openjarvis.core.config.load_config", return_value=config),
        mock.patch("openjarvis.speech.clap.wait_for_double_clap", return_value=True),
        mock.patch("openjarvis.cli._voice_chat.record_voice", return_value="status"),
        mock.patch(
            "openjarvis.cli._voice_chat.speak",
            side_effect=lambda text, *a, **k: spoken.append(text),
        ),
        mock.patch("openjarvis.sdk.Jarvis", return_value=fake_jarvis),
        mock.patch("openjarvis.cli.listen_cmd._warm_up_voice"),
    ):
        result = CliRunner().invoke(cli, ["listen", "--once"])

    assert result.exit_code == 0, result.output
    assert "bata duas palmas" in result.output
    assert spoken == ["Pois não, Julio?", "Tudo certo."]
    prompt = fake_jarvis.ask.call_args.args[0]
    assert "português do Brasil" in prompt and prompt.endswith("status")
