"""CLI: the schedule command writes reports and reports a valid baseline."""

from pathlib import Path

from typer.testing import CliRunner

from fleetwave.cli import app

CONFIG = Path(__file__).resolve().parents[1] / "config" / "fleet.yaml"


def test_schedule_baseline_writes_reports(tmp_path: Path) -> None:
    res = CliRunner().invoke(app, ["schedule", "-c", str(CONFIG), "-o", str(tmp_path)])
    assert res.exit_code == 0, res.output
    assert "constraints     : OK" in res.output
    assert (tmp_path / "baseline_gantt.html").stat().st_size > 1000
    assert (tmp_path / "baseline_schedule.csv").read_text().startswith("cluster,")


def test_schedule_unknown_method(tmp_path: Path) -> None:
    res = CliRunner().invoke(
        app, ["schedule", "-c", str(CONFIG), "-o", str(tmp_path), "--method", "magic"]
    )
    assert res.exit_code != 0
