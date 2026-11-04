"""Independent checker: lists every constraint a schedule violates.

Used by tests for both the baseline and (Phase 2) the CP-SAT optimiser, so the two are judged
by the same rules. An empty list means the schedule is valid.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from fleetwave.models import ENV_ORDER, Env, FleetConfig, Schedule, ScheduledTask, TaskKind
from fleetwave.scheduler.calendar import WorkCalendar


def validate_schedule(
    schedule: Schedule, fleet: FleetConfig, cal: WorkCalendar, max_parallel: int | None = None
) -> list[str]:
    """Return human-readable violations (empty if the schedule respects every constraint)."""
    cap = fleet.capacity
    max_parallel = max_parallel or cap.max_parallel_upgrades
    errors: list[str] = []
    by_cluster: dict[str, list[ScheduledTask]] = defaultdict(list)
    for t in schedule.tasks:
        by_cluster[t.cluster].append(t)

    for c in fleet.clusters:
        tasks = sorted(by_cluster.get(c.name, []), key=lambda t: t.start)
        ups = {t.env: t for t in tasks if t.kind is TaskKind.UPGRADE}
        counts = Counter(t.env for t in tasks if t.kind is TaskKind.UPGRADE)
        for e in ENV_ORDER:
            if counts[e] != 1:
                errors.append(f"{c.name}/{e}: expected 1 upgrade task, found {counts[e]}")
        if len(ups) < len(ENV_ORDER):
            continue

        # Environment order + soak (applies to upgrade and rework tasks).
        for t in tasks:
            if t.kind is TaskKind.REMEDIATION or t.env is Env.DEV:
                continue
            prev_env = ENV_ORDER[ENV_ORDER.index(t.env) - 1]
            prev = [
                p
                for p in tasks
                if p.env is prev_env and p.kind is not TaskKind.REMEDIATION and p.start < t.start
            ]
            if not prev:
                errors.append(f"{c.name}/{t.env}: starts before any {prev_env} work")
                continue
            last = max(prev, key=lambda p: p.end)
            soak = 0 if last.kind is TaskKind.REWORK else c.env(prev_env).soak_days
            ready = last.end + soak
            if t.start < ready:
                errors.append(f"{c.name}/{t.env}: starts day {t.start}, soak ends day {ready}")

        # Cross-cluster dependencies: same environment, after the dependency's upgrade finished.
        for dep in c.depends_on:
            dep_ups = {t.env: t for t in by_cluster.get(dep, []) if t.kind is TaskKind.UPGRADE}
            for e in ENV_ORDER:
                if e in dep_ups and ups[e].start < dep_ups[e].end:
                    errors.append(f"{c.name}/{e}: starts before dependency {dep} is ready")

        # CAB: approval at a CAB held after pre-prod evidence is ready and before prod starts.
        prod = ups[Env.PROD]
        pre = [t for t in tasks if t.env is Env.PREPROD and t.start < prod.start]
        if pre:
            last = max(pre, key=lambda t: t.end)
            soak = 0 if last.kind is TaskKind.REWORK else c.env(Env.PREPROD).soak_days
            evidence = last.end + soak
            if not any(evidence <= k < prod.start for k in cal.cab_days):
                errors.append(f"{c.name}/prod: no CAB between evidence day {evidence} and start")

    for t in schedule.tasks:
        if t.kind is TaskKind.REMEDIATION:
            continue  # code/config fixes are not environment changes
        for k in t.days:
            if cal.is_frozen(k, t.env):
                errors.append(f"{t.cluster}/{t.env}: runs on frozen day {cal.date(k)}")
                break
            if t.env is Env.PROD and cal.date(k).weekday() not in cal.cfg.prod_weekdays:
                errors.append(f"{t.cluster}/prod: runs on disallowed weekday {cal.date(k)}")
                break

    prod_tasks = [t for t in schedule.tasks if t.env is Env.PROD and t.kind is TaskKind.UPGRADE]
    per_week = Counter(cal.week(t.start) for t in prod_tasks)
    for week, n in per_week.items():
        if n > cap.max_prod_per_week:
            errors.append(f"week {week}: {n} prod upgrades > cap {cap.max_prod_per_week}")

    tier1 = {c.name for c in fleet.clusters if c.tier == 1}
    t1_day = Counter(k for t in prod_tasks if t.cluster in tier1 for k in t.days)
    for k, n in t1_day.items():
        if n > cap.max_tier1_prod_per_day:
            errors.append(f"{cal.date(k)}: {n} tier-1 prod upgrades on one day")

    load = Counter(k for t in schedule.tasks if t.kind is not TaskKind.REMEDIATION for k in t.days)
    for k, n in sorted(load.items()):
        if n > max_parallel:
            errors.append(f"{cal.date(k)}: {n} concurrent tasks > capacity {max_parallel}")
    return errors
