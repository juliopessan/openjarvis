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
    ):
        result = CliRunner().invoke(cli, ["listen", "--once"])

    assert result.exit_code == 0, result.output
    assert spoken == ["Yes, Julio?", "All systems nominal."]
    fake_jarvis.ask.assert_called_once_with("status report", agent=None)
    fake_jarvis.close.assert_called_once()
