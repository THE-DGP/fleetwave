"""Schema validation: good config loads, bad config is rejected with a clear error."""

import pytest
from pydantic import ValidationError

from fleetwave.models import ENV_ORDER, Env, FleetConfig, StageDuration, load_fleet


def test_fleet_yaml_loads(fleet: FleetConfig) -> None:
    assert len(fleet.clusters) == 10
    for c in fleet.clusters:
        assert set(c.environments) == set(ENV_ORDER)
        assert 1 <= c.tier <= 3


def test_stage_duration_order_enforced() -> None:
    with pytest.raises(ValidationError, match="min <= likely <= max"):
        StageDuration(min=2, likely=1, max=3)


def test_stage_duration_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        StageDuration(min=0, likely=1, max=2)


def test_pert_mean() -> None:
    assert StageDuration(min=1, likely=2, max=9).pert_mean == pytest.approx(3.0)


def test_task_days_rounds_up(fleet: FleetConfig) -> None:
    spec = fleet.cluster("identity").env(Env.TEST)  # 0.5 + 1.5
    assert spec.task_days() == 2
    assert spec.task_days(upgrade=0.25, test=0.5) == 1


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda d: d["clusters"][2]["depends_on"].append("nope"), "unknown cluster"),
        (lambda d: d["clusters"][0]["depends_on"].append("identity"), "depends on itself"),
        (lambda d: d["clusters"][0]["depends_on"].append("cards"), "dependency cycle"),
        (lambda d: d["clusters"][1].update(name="identity"), "duplicate cluster names"),
        (lambda d: d["clusters"][0]["environments"].pop("prod"), "missing environments"),
        (lambda d: d.update(surprise=1), "Extra inputs"),
        (lambda d: d["calendar"].update(cab_weekday="sat"), "unknown weekday"),
        (lambda d: d["calendar"]["freezes"][0].update(end="2027-01-01"), "ends before it starts"),
        (lambda d: d["clusters"][0].update(tier=4), "less than or equal to 3"),
    ],
)
def test_invalid_config_rejected(fleet_dict: dict, mutate, message: str) -> None:
    mutate(fleet_dict)
    with pytest.raises(ValidationError, match=message):
        FleetConfig.model_validate(fleet_dict)


def test_weekday_names_parsed(fleet: FleetConfig) -> None:
    assert fleet.calendar.prod_weekdays == [1, 2, 3]  # tue, wed, thu
    assert fleet.calendar.cab_weekday == 3


def test_weekday_integer_out_of_range(fleet_dict: dict) -> None:
    fleet_dict["calendar"]["prod_weekdays"] = [6]
    with pytest.raises(ValidationError, match=r"mon\.\.fri or 0\.\.4"):
        FleetConfig.model_validate(fleet_dict)


def test_topological_order_respects_dependencies(fleet: FleetConfig) -> None:
    order = fleet.topological_order()
    pos = {n: i for i, n in enumerate(order)}
    for c in fleet.clusters:
        for d in c.depends_on:
            assert pos[d] < pos[c.name]


def test_cluster_lookup(fleet: FleetConfig) -> None:
    assert fleet.cluster("cards").tier == 1
    with pytest.raises(KeyError):
        fleet.cluster("missing")


def test_load_fleet_rejects_non_mapping(tmp_path) -> None:
    p = tmp_path / "bad.yaml"
    p.write_text("- just\n- a list\n")
    with pytest.raises(ValueError, match="mapping"):
        load_fleet(p)
