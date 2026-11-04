"""FleetWave command-line interface (Typer).

Commands are added phase by phase: ``schedule`` (Phase 1-2), ``simulate`` (Phase 3),
``scan`` (Phase 4), ``report`` / ``run`` (Phase 5).
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from fleetwave import __version__
from fleetwave.models import TaskKind, load_fleet
from fleetwave.scheduler.baseline import simulate_baseline
from fleetwave.scheduler.calendar import WorkCalendar
from fleetwave.scheduler.validate import validate_schedule
from fleetwave.viz import gantt, schedule_frame

app = typer.Typer(
    name="fleetwave",
    help="Kubernetes fleet upgrade readiness scanner and upgrade-wave scheduler.",
    no_args_is_help=True,
)

ConfigOpt = Annotated[Path, typer.Option("--config", "-c", help="Fleet definition YAML.")]
OutOpt = Annotated[Path, typer.Option("--out", "-o", help="Directory for reports.")]


@app.callback()
def main() -> None:
    """FleetWave CLI root (keeps Typer in multi-command mode)."""


@app.command()
def version() -> None:
    """Print the installed FleetWave version."""
    typer.echo(f"fleetwave {__version__}")


@app.command()
def schedule(
    config: ConfigOpt = Path("config/fleet.yaml"),
    method: Annotated[
        str, typer.Option(help="baseline (optimise arrives in Phase 2)")
    ] = "baseline",
    out: OutOpt = Path("reports"),
) -> None:
    """Build a schedule, check it against every constraint and write Gantt + CSV."""
    fleet = load_fleet(config)
    cal = WorkCalendar(fleet.calendar)
    if method != "baseline":
        raise typer.BadParameter(f"unknown method {method!r}", param_hint="--method")
    sched = simulate_baseline(fleet, cal)
    errors = validate_schedule(sched, fleet, cal)

    out.mkdir(parents=True, exist_ok=True)
    html = out / f"{method}_gantt.html"
    csv = out / f"{method}_schedule.csv"
    gantt(sched, fleet, cal).write_html(html, include_plotlyjs="cdn")
    schedule_frame(sched, fleet, cal).to_csv(csv, index=False)

    rework = sum(1 for t in sched.tasks if t.kind is TaskKind.REWORK)
    typer.echo(f"method          : {sched.method}")
    typer.echo(f"clusters / envs : {len(fleet.clusters)} / 4")
    typer.echo(f"start -> finish : {sched.start_date} -> {sched.finish_date}")
    typer.echo(
        f"makespan        : {sched.makespan_calendar_days} calendar days "
        f"({sched.makespan_working_days} working days)"
    )
    typer.echo(f"rework tasks    : {rework}")
    typer.echo(f"constraints     : {'OK' if not errors else f'{len(errors)} VIOLATIONS'}")
    for e in errors[:20]:
        typer.echo(f"  - {e}")
    typer.echo(f"wrote           : {html}, {csv}")
    if errors:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
