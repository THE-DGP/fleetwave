"""Baseline simulator: lands in the 60-90 day band and obeys every constraint."""

from collections import Counter

import pytest

from fleetwave.models import ENV_ORDER, Env, FleetConfig, TaskKind
from fleetwave.scheduler.baseline import (
    expected_late_blockers,
    likely_durations,
    simulate_baseline,
)
from fleetwave.scheduler.calendar import WorkCalendar
from fleetwave.scheduler.validate import validate_schedule


@pytest.fixture(scope="module")
def sched(fleet: FleetConfig, cal: WorkCalendar):
    return simulate_baseline(fleet, cal)


def test_baseline_lands_in_60_to_90_days(sched) -> None:
    assert 60 <= sched.makespan_calendar_days <= 90


def test_baseline_respects_all_constraints(sched, fleet, cal) -> None:
    assert validate_schedule(sched, fleet, cal) == []


def test_baseline_uses_at_most_its_streams(sched, fleet) -> None:
    load = Counter(k for t in sched.tasks if t.kind is not TaskKind.REMEDIATION for k in t.days)
    assert max(load.values()) <= fleet.baseline.parallel_streams


def test_every_cluster_env_upgraded_once(sched, fleet) -> None:
    ups = Counter((t.cluster, t.env) for t in sched.tasks if t.kind is TaskKind.UPGRADE)
    assert ups == Counter({(c.name, e): 1 for c in fleet.clusters for e in ENV_ORDER})


def test_gated_waves(sched, fleet) -> None:
    """No test upgrade starts until every dev upgrade has finished and soaked."""
    for gated in fleet.baseline.gated_envs:
        prev = ENV_ORDER[ENV_ORDER.index(gated) - 1]
        prev_done = max(
            t.end + fleet.cluster(t.cluster).env(prev).soak_days
            for t in sched.tasks
            if t.env is prev and t.kind is TaskKind.UPGRADE
        )
        first = min(t.start for t in sched.tasks if t.env is gated and t.kind is TaskKind.UPGRADE)
        assert first >= prev_done


def test_late_blockers_create_rework(sched, fleet) -> None:
    late = expected_late_blockers(fleet)
    for c in fleet.clusters:
        kinds = Counter(t.kind for t in sched.tasks if t.cluster == c.name)
        if late[c.name]:
            assert kinds[TaskKind.REMEDIATION] == 1
            assert kinds[TaskKind.REWORK] == 2
        else:
            assert kinds[TaskKind.REWORK] == 0


def test_late_discovery_costs_time(fleet, cal, sched) -> None:
    clean = simulate_baseline(fleet, cal, late_blockers={})
    assert clean.makespan_working_days < sched.makespan_working_days
    assert validate_schedule(clean, fleet, cal) == []


def test_deterministic(fleet, cal, sched) -> None:
    assert simulate_baseline(fleet, cal) == sched


def test_custom_durations_are_used(fleet, cal, sched) -> None:
    slow = simulate_baseline(fleet, cal, durations=lambda c, e: likely_durations(c, e) + 1)
    assert slow.makespan_working_days > sched.makespan_working_days


def test_single_stream_is_slower(fleet_dict, cal, sched) -> None:
    fleet_dict["baseline"]["parallel_streams"] = 1
    one = simulate_baseline(FleetConfig.model_validate(fleet_dict), cal)
    assert one.makespan_working_days > sched.makespan_working_days


def test_prod_changes_wait_for_cab(sched, fleet, cal) -> None:
    for t in sched.tasks:
        if t.env is Env.PROD:
            assert any(k < t.start for k in cal.cab_days)


def test_horizon_too_short_raises(fleet_dict) -> None:
    fleet_dict["calendar"]["horizon_working_days"] = 30
    short = FleetConfig.model_validate(fleet_dict)
    with pytest.raises((RuntimeError, ValueError), match="horizon"):
        simulate_baseline(short)
