"""Pydantic schemas for the fleet definition, calendar constraints and schedules.

All durations are in *working days* (Mon-Fri excluding bank holidays). Soak times are also
counted in working days because soak sign-off needs people watching dashboards.
"""

from __future__ import annotations

import datetime as dt
import math
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Env(StrEnum):
    """Deployment environments, in promotion order."""

    DEV = "dev"
    TEST = "test"
    PREPROD = "preprod"
    PROD = "prod"


ENV_ORDER: tuple[Env, ...] = (Env.DEV, Env.TEST, Env.PREPROD, Env.PROD)

WEEKDAYS: dict[str, int] = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4}


def _weekday(value: Any) -> int:
    """Accept 'tue' style names or 0-4 integers and return Python's weekday number."""
    if isinstance(value, str):
        key = value.strip().lower()[:3]
        if key not in WEEKDAYS:
            raise ValueError(f"unknown weekday {value!r}; use mon..fri")
        return WEEKDAYS[key]
    if isinstance(value, int) and 0 <= value <= 4:
        return value
    raise ValueError(f"weekday must be mon..fri or 0..4, got {value!r}")


class _Model(BaseModel):
    """Base model: unknown keys are errors and instances are immutable."""

    model_config = ConfigDict(extra="forbid", frozen=True)


# --------------------------------------------------------------------------- fleet


class StageDuration(_Model):
    """Three-point estimate (working days) used for PERT/triangular sampling."""

    min: float = Field(gt=0)
    likely: float = Field(gt=0)
    max: float = Field(gt=0)

    @model_validator(mode="after")
    def _check_order(self) -> StageDuration:
        if not self.min <= self.likely <= self.max:
            raise ValueError(f"need min <= likely <= max, got {self.min}/{self.likely}/{self.max}")
        return self

    @property
    def pert_mean(self) -> float:
        """PERT expected value: (min + 4*likely + max) / 6."""
        return (self.min + 4 * self.likely + self.max) / 6


class EnvironmentSpec(_Model):
    """Work needed to upgrade one environment of one cluster."""

    upgrade: StageDuration
    test: StageDuration
    soak_days: int = Field(ge=0)

    def task_days(self, upgrade: float | None = None, test: float | None = None) -> int:
        """Whole working days the task occupies (defaults to the likely estimates)."""
        up = self.upgrade.likely if upgrade is None else upgrade
        te = self.test.likely if test is None else test
        return max(1, math.ceil(up + te - 1e-9))


class Cluster(_Model):
    """One AKS cluster serving one business service."""

    name: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    tier: int = Field(ge=1, le=3, description="1 = most critical")
    environments: dict[Env, EnvironmentSpec]
    depends_on: list[str] = Field(default_factory=list)
    latent_blockers: int = Field(
        default=0, ge=0, description="Upgrade blockers present today (later: from the scanner)"
    )

    @field_validator("environments")
    @classmethod
    def _all_envs(cls, v: dict[Env, EnvironmentSpec]) -> dict[Env, EnvironmentSpec]:
        missing = [e.value for e in ENV_ORDER if e not in v]
        if missing:
            raise ValueError(f"missing environments: {missing}")
        return v

    def env(self, env: Env) -> EnvironmentSpec:
        """Return the spec for one environment."""
        return self.environments[env]


# --------------------------------------------------------------------------- calendar


class MonthEndFreeze(_Model):
    """Freeze the last N working days of every month."""

    working_days: int = Field(default=3, ge=1)
    envs: list[Env] = Field(default_factory=lambda: [Env.PROD])


class PaydayFreeze(_Model):
    """Freeze a window of working days around payday (rolled back to a working day)."""

    day_of_month: int = Field(default=25, ge=1, le=28)
    days_before: int = Field(default=1, ge=0)
    days_after: int = Field(default=1, ge=0)
    envs: list[Env] = Field(default_factory=lambda: [Env.PROD])


class FreezeWindow(_Model):
    """An explicit change freeze, inclusive of both dates."""

    name: str
    start: dt.date
    end: dt.date
    envs: list[Env]

    @model_validator(mode="after")
    def _check_dates(self) -> FreezeWindow:
        if self.end < self.start:
            raise ValueError(f"freeze {self.name!r} ends before it starts")
        return self


class CalendarConfig(_Model):
    """Working calendar, change windows, CAB and freezes."""

    start_date: dt.date
    horizon_working_days: int = Field(default=260, ge=20)
    bank_holidays: list[dt.date] = Field(default_factory=list)
    prod_weekdays: list[int] = Field(default_factory=lambda: [1, 2, 3])
    cab_weekday: int = 3
    month_end: MonthEndFreeze | None = None
    payday: PaydayFreeze | None = None
    freezes: list[FreezeWindow] = Field(default_factory=list)

    @field_validator("prod_weekdays", mode="before")
    @classmethod
    def _parse_days(cls, v: list[Any]) -> list[int]:
        return sorted({_weekday(x) for x in v})

    @field_validator("cab_weekday", mode="before")
    @classmethod
    def _parse_cab(cls, v: Any) -> int:
        return _weekday(v)


class Capacity(_Model):
    """Fleet-wide limits."""

    max_parallel_upgrades: int = Field(default=2, ge=1)
    max_prod_per_week: int = Field(default=3, ge=1)
    max_tier1_prod_per_day: int = Field(default=1, ge=1)


class ReworkConfig(_Model):
    """What happens when a blocker is discovered late (during an environment upgrade)."""

    late_discovery_probability: float = Field(ge=0, le=1)
    discovery_env: Env = Env.PREPROD
    fix_days: StageDuration


class BaselinePolicy(_Model):
    """How today's manual process is run."""

    gated_envs: list[Env] = Field(
        default_factory=lambda: [Env.TEST, Env.PREPROD],
        description="A wave in these envs starts only when the previous env is done everywhere",
    )
    parallel_streams: int = Field(default=2, ge=1)


class FleetConfig(_Model):
    """The whole fleet definition loaded from fleet.yaml."""

    name: str
    description: str = ""
    calendar: CalendarConfig
    capacity: Capacity
    rework: ReworkConfig
    baseline: BaselinePolicy = Field(default_factory=BaselinePolicy)
    clusters: list[Cluster] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_graph(self) -> FleetConfig:
        names = [c.name for c in self.clusters]
        dupes = sorted({n for n in names if names.count(n) > 1})
        if dupes:
            raise ValueError(f"duplicate cluster names: {dupes}")
        known = set(names)
        for c in self.clusters:
            for d in c.depends_on:
                if d == c.name:
                    raise ValueError(f"cluster {c.name!r} depends on itself")
                if d not in known:
                    raise ValueError(f"cluster {c.name!r} depends on unknown cluster {d!r}")
        self.topological_order()  # raises on cycles
        return self

    def cluster(self, name: str) -> Cluster:
        """Look up a cluster by name."""
        for c in self.clusters:
            if c.name == name:
                return c
        raise KeyError(name)

    def topological_order(self) -> list[str]:
        """Cluster names with dependencies first; ties keep config order (Kahn's algorithm)."""
        remaining = {c.name: set(c.depends_on) for c in self.clusters}
        order: list[str] = []
        while remaining:
            ready = [c.name for c in self.clusters if c.name in remaining and not remaining[c.name]]
            if not ready:
                raise ValueError(f"dependency cycle among: {sorted(remaining)}")
            nxt = ready[0]
            order.append(nxt)
            del remaining[nxt]
            for deps in remaining.values():
                deps.discard(nxt)
        return order


def load_fleet(path: str | Path) -> FleetConfig:
    """Load and validate fleet.yaml. Top-level keys starting with 'x-' are YAML anchors only."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: expected a mapping at top level")
    data = {k: v for k, v in raw.items() if not str(k).startswith("x-")}
    return FleetConfig.model_validate(data)


# --------------------------------------------------------------------------- schedules


class TaskKind(StrEnum):
    """Kinds of scheduled work."""

    UPGRADE = "upgrade"
    REMEDIATION = "remediation"
    REWORK = "rework"


class ScheduledTask(_Model):
    """A block of work on working-day indices [start, end)."""

    cluster: str
    env: Env
    kind: TaskKind = TaskKind.UPGRADE
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    note: str = ""

    @model_validator(mode="after")
    def _check_span(self) -> ScheduledTask:
        if self.end <= self.start:
            raise ValueError("task end must be after start")
        return self

    @property
    def days(self) -> range:
        """Working-day indices the task occupies."""
        return range(self.start, self.end)


class Schedule(_Model):
    """A complete schedule plus headline metrics."""

    method: str
    tasks: list[ScheduledTask]
    start_date: dt.date
    finish_date: dt.date
    makespan_working_days: int
    makespan_calendar_days: int
    status: str = "n/a"
