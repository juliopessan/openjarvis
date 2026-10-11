"""``jarvis scheduler create --timezone`` stores the zone for cron evaluation."""

from pathlib import Path
from unittest import mock

from click.testing import CliRunner

from openjarvis.cli import cli
from openjarvis.scheduler.scheduler import TaskScheduler
from openjarvis.scheduler.store import SchedulerStore


def _invoke(tmp_path: Path, *extra: str):
    db = str(tmp_path / "scheduler.db")
    with mock.patch(
        "openjarvis.cli.scheduler_cmd._get_store",
        side_effect=lambda: SchedulerStore(db),
    ):
        result = CliRunner().invoke(
            cli,
            ["scheduler", "create", "hi", "--type", "cron", "--value", "0 7 * * *"]
            + list(extra),
        )
    return result, db


def test_create_with_timezone_persists_metadata(tmp_path: Path) -> None:
    result, db = _invoke(tmp_path, "--timezone", "America/Sao_Paulo")
    assert result.exit_code == 0, result.output
    assert "America/Sao_Paulo" in result.output

    store = SchedulerStore(db)
    try:
        (task,) = TaskScheduler(store).list_tasks()
    finally:
        store.close()
    assert task.metadata["timezone"] == "America/Sao_Paulo"
    # 07:00 in Sao Paulo (UTC-3) is 10:00 UTC.
    assert "T10:00:00" in task.next_run


def test_create_rejects_unknown_timezone(tmp_path: Path) -> None:
    result, _ = _invoke(tmp_path, "--timezone", "Mars/Olympus_Mons")
    assert result.exit_code != 0
    assert "Unknown timezone" in result.output
