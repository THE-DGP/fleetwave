# FleetWave

Prototype tooling to shorten a multi-cluster Kubernetes version-upgrade cycle on a
regulated multi-service banking platform, from a modelled 60–90 days towards 30 days.

- **Layer 1 – Readiness Scanner:** finds upgrade blockers per cluster and scores readiness 0–100.
- **Layer 3 – Upgrade Wave Scheduler:** Google OR-Tools CP-SAT finds the fastest safe schedule
  under change-freeze, CAB, maintenance-window and team-capacity constraints; Monte Carlo
  simulation gives P50/P80/P95 completion dates.

> Status: Phase 1 — data model, calendar and baseline simulator. Results fill in as phases land.

## Try it

```powershell
fleetwave schedule --method baseline      # prints makespan, checks constraints, writes:
start reports\baseline_gantt.html          #   Gantt chart (prod freezes shaded)
#                                          #   reports\baseline_schedule.csv
```

Baseline (today's process, modelled): see [docs/assumptions.md](docs/assumptions.md) for every
number and how it was calibrated.

## Dev quickstart (Windows PowerShell)

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
ruff check .
pytest
```

All durations and probabilities are modelled assumptions — see [docs/assumptions.md](docs/assumptions.md).
