"""Simulate today's manual upgrade process.

Model of the current process (see docs/assumptions.md):

* **Environment waves.** The team works one environment at a time across the fleet: all dev,
  then all test, then all pre-prod (including rework), then prod. A gated wave
  (``gated_envs``) also waits until the previous wave has soaked for every cluster. Prod
  changes are raised to CAB cluster by cluster once the team reaches the prod wave.
* **Fixed order, manual hand-off.** Within a wave, clusters are taken in dependency order by
  ``parallel_streams`` engineers, each doing one upgrade at a time ("one after another").
* **Late discovery.** Blockers are found when pre-prod is upgraded. Each one triggers a fix,
  a re-test in the test environment and a repeat of the pre-prod upgrade.
* **Same rules as everyone else:** freezes, Tue-Thu prod, CAB approval, weekly prod cap and
  tier-1 separation.

The simulator is deterministic by default (likely durations, expected number of late
blockers). Phase 3 passes sampled durations and blocker counts for Monte Carlo runs.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass

from fleetwave.models import (
    ENV_ORDER,
    Cluster,
    Env,
    FleetConfig,
    Schedule,
    ScheduledTask,
    TaskKind,
)
from fleetwave.scheduler.calendar import WorkCalendar

#: (cluster, env) -> whole working days for that environment's upgrade + test.
DurationFn = Callable[[Cluster, Env], int]


def likely_durations(cluster: Cluster, env: Env) -> int:
    """Default duration function: likely upgrade + likely test, rounded up to whole days."""
    return cluster.env(env).task_days()


def likely_test_durations(cluster: Cluster, env: Env) -> int:
    """Default rework duration: re-running the likely test effort only (no re-upgrade)."""
    return max(1, math.ceil(cluster.env(env).test.likely - 1e-9))


def expected_late_blockers(fleet: FleetConfig) -> dict[str, int]:
    """Deterministic blocker count per cluster: round(latent_blockers * p_late)."""
    p = fleet.rework.late_discovery_probability
    return {c.name: math.floor(c.latent_blockers * p + 0.5) for c in fleet.clusters}


@dataclass
class _ProdBook:
    """Tracks prod bookings so the weekly cap and tier-1 separation hold."""

    cal: WorkCalendar
    fleet: FleetConfig
    per_week: Counter[int]
    tier1_days: Counter[int]

    def ok(self, cluster: Cluster, start: int, days: int) -> bool:
        cap = self.fleet.capacity
        if self.per_week[self.cal.week(start)] >= cap.max_prod_per_week:
            return False
        if cluster.tier == 1:
            return all(
                self.tier1_days[k] < cap.max_tier1_prod_per_day for k in range(start, start + days)
            )
        return True

    def book(self, cluster: Cluster, start: int, days: int) -> None:
        self.per_week[self.cal.week(start)] += 1
        if cluster.tier == 1:
            for k in range(start, start + days):
                self.tier1_days[k] += 1


def simulate_baseline(
    fleet: FleetConfig,
    cal: WorkCalendar | None = None,
    durations: DurationFn = likely_durations,
    rework_durations: DurationFn = likely_test_durations,
    late_blockers: dict[str, int] | None = None,
    fix_days: Callable[[int], int] | None = None,
) -> Schedule:
    """Return the schedule today's process would produce.

    Within each environment wave the team works greedily: whenever an engineer is free they
    pick up the ready job that can start soonest (ties go to dependency order). Remediation
    is done by application teams, so it adds elapsed time but uses no platform capacity.

    Args:
        fleet: validated fleet configuration.
        cal: calendar (built from the fleet config if omitted).
        durations: function giving whole working days per (cluster, env) task.
        rework_durations: working days to re-test / re-verify an env after a fix.
        late_blockers: blockers found late per cluster (default: expected value).
        fix_days: function blockers -> remediation working days (default: likely fix each).
    """
    cal = cal or WorkCalendar(fleet.calendar)
    late = expected_late_blockers(fleet) if late_blockers is None else late_blockers
    if fix_days is None:
        fix_days = lambda n: math.ceil(n * fleet.rework.fix_days.likely)  # noqa: E731
    streams = [0] * fleet.baseline.parallel_streams
    book = _ProdBook(cal, fleet, Counter(), Counter())
    tasks: list[ScheduledTask] = []
    done: dict[tuple[str, Env], int] = {}  # (cluster, env) -> day all work in that env ended
    order = [fleet.cluster(n) for n in fleet.topological_order()]
    rank = {c.name: i for i, c in enumerate(order)}

    def feasible(c: Cluster, env: Env, kind: TaskKind, days: int, start: int) -> int:
        """First day >= start on which the task may run."""
        while True:
            if start + days > cal.horizon:
                raise RuntimeError("baseline does not fit in the calendar horizon")
            freeze_ok = kind is TaskKind.REMEDIATION or cal.can_run(env, start, days)
            prod_ok = env is not Env.PROD or book.ok(c, start, days)
            if freeze_ok and prod_ok:
                return start
            start += 1

    def env_ready(c: Cluster, env: Env) -> int | None:
        """Earliest start for c's first job in env, or None if a dependency is unfinished."""
        r = gate
        i = ENV_ORDER.index(env)
        if i > 0:
            prev = ENV_ORDER[i - 1]
            r = max(r, done[(c.name, prev)] + c.env(prev).soak_days)
        for d in c.depends_on:
            if (d, env) not in done:
                return None
            r = max(r, done[(d, env)])
        return cal.earliest_prod_start(r) if env is Env.PROD else r

    for env in ENV_ORDER:
        gate = 0
        if env in fleet.baseline.gated_envs and env is not Env.DEV:
            prev = ENV_ORDER[ENV_ORDER.index(env) - 1]
            gate = max(done[(c.name, prev)] + c.env(prev).soak_days for c in order)
        # Each cluster's job chain for this wave: (env, kind, days, note).
        chains: dict[str, list[tuple[Env, TaskKind, int, str]]] = {}
        for c in order:
            chain = [(env, TaskKind.UPGRADE, durations(c, env), "")]
            n = late.get(c.name, 0)
            if env is fleet.rework.discovery_env and n > 0:
                prev = ENV_ORDER[ENV_ORDER.index(env) - 1]
                chain += [
                    (env, TaskKind.REMEDIATION, fix_days(n), f"{n} blocker(s) found late"),
                    (prev, TaskKind.REWORK, rework_durations(c, prev), "re-test"),
                    (env, TaskKind.REWORK, rework_durations(c, env), "re-verify"),
                ]
            chains[c.name] = chain
        next_ready: dict[str, int] = {}
        while chains:
            s_idx = min(range(len(streams)), key=lambda i: streams[i])
            best: tuple[int, int, Cluster] | None = None
            for c in order:
                if c.name not in chains:
                    continue
                if c.name not in next_ready:
                    r = env_ready(c, env)
                    if r is None:
                        continue
                    next_ready[c.name] = r
                job_env, kind, days, _ = chains[c.name][0]
                floor = next_ready[c.name]
                if kind is not TaskKind.REMEDIATION:
                    floor = max(floor, streams[s_idx])
                start = feasible(c, job_env, kind, days, floor)
                if best is None or (start, rank[c.name]) < (best[0], rank[best[2].name]):
                    best = (start, rank[c.name], c)
            if best is None:
                raise RuntimeError("baseline deadlock: unsatisfiable dependencies")
            start, _, c = best
            job_env, kind, days, note = chains[c.name].pop(0)
            end = start + days
            tasks.append(
                ScheduledTask(
                    cluster=c.name, env=job_env, kind=kind, start=start, end=end, note=note
                )
            )
            if job_env is Env.PROD:
                book.book(c, start, days)
            if kind is not TaskKind.REMEDIATION:
                streams[s_idx] = end
            # The next job in the chain waits for this one. No extra soak after a re-test:
            # the version change already soaked; the fix is verified by the regression run.
            next_ready[c.name] = end
            if not chains[c.name]:
                del chains[c.name]
                done[(c.name, env)] = end

    finish = max(t.end for t in tasks)
    return Schedule(
        method="baseline",
        tasks=sorted(tasks, key=lambda t: (t.start, t.cluster)),
        start_date=fleet.calendar.start_date,
        finish_date=cal.date(finish - 1),
        makespan_working_days=finish,
        makespan_calendar_days=cal.calendar_days(finish),
    )
