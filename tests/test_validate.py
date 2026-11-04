"""The independent schedule checker catches each kind of violation.

These tests matter because Phase 2's CP-SAT tests rely on the same checker: if the checker
can detect a violation, a clean result from it is meaningful.
"""

import datetime as dt

import pytest

from fleetwave.models import Env, Schedule, ScheduledTask, TaskKind
from fleetwave.scheduler.baseline import simulate_baseline
from fleetwave.scheduler.validate import validate_schedule


@pytest.fixture(scope="module")
def base(fleet, cal) -> Schedule:
    return simulate_baseline(fleet, cal)


def _replace(sched: Schedule, cluster: str, env: Env, **changes) -> Schedule:
    tasks = []
    for t in sched.tasks:
        if t.cluster == cluster and t.env is env and t.kind is TaskKind.UPGRADE:
            t = t.model_copy(update=changes)
        tasks.append(t)
    return sched.model_copy(update={"tasks": tasks})


def _prod(sched: Schedule, cluster: str) -> ScheduledTask:
    return next(
        t
        for t in sched.tasks
        if t.cluster == cluster and t.env is Env.PROD and t.kind is TaskKind.UPGRADE
    )


def _errors(sched, fleet, cal, **kw) -> str:
    return "\n".join(validate_schedule(sched, fleet, cal, **kw))


def test_missing_task_detected(base, fleet, cal) -> None:
    bad = base.model_copy(
        update={"tasks": [t for t in base.tasks if t.cluster != "cards" or t.env is not Env.PROD]}
    )
    assert "cards/prod: expected 1 upgrade task, found 0" in _errors(bad, fleet, cal)


def test_env_order_violation_detected(base, fleet, cal) -> None:
    dev = next(t for t in base.tasks if t.cluster == "lending" and t.env is Env.DEV)
    bad = _replace(base, "lending", Env.TEST, start=dev.end, end=dev.end + 1)  # skips soak
    assert "lending/test" in _errors(bad, fleet, cal)


def test_dependency_violation_detected(base, fleet, cal) -> None:
    bad = _replace(base, "payments", Env.DEV, start=0, end=1)  # alongside identity's dev
    assert "starts before dependency identity" in _errors(bad, fleet, cal)


def test_prod_weekday_violation_detected(base, fleet, cal) -> None:
    p = _prod(base, "lending")
    k = next(k for k in range(p.start, cal.horizon) if cal.date(k).weekday() == 4)  # a Friday
    bad = _replace(base, "lending", Env.PROD, start=k, end=k + 1)
    assert "disallowed weekday" in _errors(bad, fleet, cal)


def test_freeze_violation_detected(base, fleet, cal) -> None:
    k = cal.index_on_or_after(dt.date(2027, 4, 6))  # peak freeze, a Tuesday
    bad = _replace(base, "lending", Env.PROD, start=k, end=k + 1)
    assert "frozen day 2027-04-06" in _errors(bad, fleet, cal)


def test_cab_violation_detected(base, fleet, cal) -> None:
    pre = max(
        (t for t in base.tasks if t.cluster == "lending" and t.env is Env.PREPROD),
        key=lambda t: t.end,
    )
    soak = 0 if pre.kind is TaskKind.REWORK else fleet.cluster("lending").env(Env.PREPROD).soak_days
    evidence = pre.end + soak
    k = next(
        k
        for k in range(evidence, cal.horizon)
        if cal.is_prod_day(k) and not any(evidence <= c < k for c in cal.cab_days)
    )
    bad = _replace(base, "lending", Env.PROD, start=k, end=k + 1)
    assert "lending/prod: no CAB" in _errors(bad, fleet, cal)


def test_weekly_prod_cap_violation_detected(base, fleet, cal) -> None:
    week = cal.week(_prod(base, "identity").start)
    tasks = list(base.tasks)
    for extra in ("x1", "x2", "x3"):
        p = _prod(base, "identity")
        tasks.append(p.model_copy(update={"cluster": extra}))
    bad = base.model_copy(update={"tasks": tasks})
    assert f"week {week}:" in _errors(bad, fleet, cal)


def test_tier1_same_day_violation_detected(base, fleet, cal) -> None:
    ident = _prod(base, "identity")
    bad = _replace(base, "mobile-banking", Env.PROD, start=ident.start, end=ident.end)
    assert "tier-1 prod upgrades on one day" in _errors(bad, fleet, cal)


def test_capacity_violation_detected(base, fleet, cal) -> None:
    assert "concurrent tasks > capacity 1" in _errors(base, fleet, cal, max_parallel=1)


def test_remediation_does_not_use_platform_capacity(base, fleet, cal) -> None:
    rem = next(t for t in base.tasks if t.kind is TaskKind.REMEDIATION)
    extra = [rem.model_copy(update={"cluster": rem.cluster}) for _ in range(5)]
    ok = base.model_copy(update={"tasks": [*base.tasks, *extra]})
    assert "capacity" not in _errors(ok, fleet, cal)
