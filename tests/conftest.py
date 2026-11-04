"""Shared fixtures: the real fleet config and its calendar."""

from pathlib import Path

import pytest

from fleetwave.models import FleetConfig, load_fleet
from fleetwave.scheduler.calendar import WorkCalendar

CONFIG = Path(__file__).resolve().parents[1] / "config" / "fleet.yaml"


@pytest.fixture(scope="session")
def fleet() -> FleetConfig:
    return load_fleet(CONFIG)


@pytest.fixture(scope="session")
def cal(fleet: FleetConfig) -> WorkCalendar:
    return WorkCalendar(fleet.calendar)


@pytest.fixture
def fleet_dict(fleet: FleetConfig) -> dict:
    """A mutable copy of the config, for building invalid variants."""
    return fleet.model_dump(mode="json")
