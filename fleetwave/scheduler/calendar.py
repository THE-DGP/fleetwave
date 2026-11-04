"""Working-day calendar shared by the baseline simulator and the CP-SAT optimiser.

Time is an integer index into the list of working days starting at ``start_date``.
Index 0 is the start date (if it is a working day). Task intervals are [start, end).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable

from fleetwave.models import ENV_ORDER, CalendarConfig, Env

_ONE_DAY = dt.timedelta(days=1)


class WorkCalendar:
    """Maps working-day indices to dates and answers freeze / change-window questions."""

    def __init__(self, cfg: CalendarConfig) -> None:
        self.cfg = cfg
        self._holidays = set(cfg.bank_holidays)
        self.days: list[dt.date] = []
        d = cfg.start_date
        while len(self.days) < cfg.horizon_working_days:
            if self.is_working_date(d):
                self.days.append(d)
            d += _ONE_DAY
        self._index = {day: i for i, day in enumerate(self.days)}
        self.frozen: dict[Env, dict[int, str]] = {e: {} for e in ENV_ORDER}
        self._build_freezes()
        self.cab_days: list[int] = [
            i for i, day in enumerate(self.days) if day.weekday() == cfg.cab_weekday
        ]

    # ------------------------------------------------------------------ basics
    @property
    def horizon(self) -> int:
        """Number of working days modelled."""
        return len(self.days)

    def is_working_date(self, d: dt.date) -> bool:
        """Mon-Fri and not a bank holiday."""
        return d.weekday() < 5 and d not in self._holidays

    def date(self, k: int) -> dt.date:
        """Date of working-day index k."""
        return self.days[k]

    def index_on_or_after(self, d: dt.date) -> int:
        """Index of the first working day on or after d."""
        while d not in self._index:
            if d > self.days[-1]:
                raise ValueError(f"{d} is beyond the calendar horizon")
            d += _ONE_DAY
        return self._index[d]

    def week(self, k: int) -> int:
        """Week number (0-based) counted in Monday-start weeks from the start date."""
        start_monday = self.cfg.start_date - dt.timedelta(days=self.cfg.start_date.weekday())
        return (self.days[k] - start_monday).days // 7

    def calendar_days(self, end_exclusive: int) -> int:
        """Elapsed calendar days from start_date to the last working day before end_exclusive."""
        return (self.days[end_exclusive - 1] - self.cfg.start_date).days + 1

    # ------------------------------------------------------------------ freezes
    def _freeze(self, indices: Iterable[int], envs: Iterable[Env], reason: str) -> None:
        for e in envs:
            for k in indices:
                self.frozen[e].setdefault(k, reason)

    def _working_dates_in_month(self, year: int, month: int) -> list[dt.date]:
        d = dt.date(year, month, 1)
        out = []
        while d.month == month:
            if self.is_working_date(d):
                out.append(d)
            d += _ONE_DAY
        return out

    def _build_freezes(self) -> None:
        months = sorted({(d.year, d.month) for d in self.days})
        if self.cfg.month_end is not None:
            me = self.cfg.month_end
            for y, m in months:
                last = self._working_dates_in_month(y, m)[-me.working_days :]
                self._freeze(
                    (self._index[d] for d in last if d in self._index), me.envs, "month-end"
                )
        if self.cfg.payday is not None:
            pd = self.cfg.payday
            for y, m in months:
                payday = dt.date(y, m, pd.day_of_month)
                while not self.is_working_date(payday):
                    payday -= _ONE_DAY
                if payday not in self._index:
                    continue
                p = self._index[payday]
                lo, hi = max(0, p - pd.days_before), min(self.horizon, p + pd.days_after + 1)
                self._freeze(range(lo, hi), pd.envs, "payday")
        for fw in self.cfg.freezes:
            idx = [i for i, d in enumerate(self.days) if fw.start <= d <= fw.end]
            self._freeze(idx, fw.envs, fw.name)

    def is_frozen(self, k: int, env: Env) -> bool:
        """True if no change may run in ``env`` on working day k."""
        return k in self.frozen[env]

    def is_prod_day(self, k: int) -> bool:
        """True if k is an allowed production weekday and not frozen for prod."""
        return self.days[k].weekday() in self.cfg.prod_weekdays and not self.is_frozen(k, Env.PROD)

    def can_run(self, env: Env, start: int, duration: int) -> bool:
        """True if a task in ``env`` may occupy every day of [start, start+duration)."""
        if start < 0 or start + duration > self.horizon:
            return False
        for k in range(start, start + duration):
            if self.is_frozen(k, env):
                return False
            if env is Env.PROD and not self.is_prod_day(k):
                return False
        return True

    # ------------------------------------------------------------------ CAB
    def first_cab_on_or_after(self, k: int) -> int:
        """Index of the first CAB meeting on or after working day k."""
        for c in self.cab_days:
            if c >= k:
                return c
        raise ValueError("no CAB within horizon")

    def earliest_prod_start(self, evidence_ready: int) -> int:
        """Earliest prod start: the day after the first CAB held once pre-prod evidence is ready."""
        return self.first_cab_on_or_after(evidence_ready) + 1

    def freeze_ranges(self, env: Env) -> list[tuple[dt.date, dt.date, str]]:
        """Contiguous frozen spans for ``env`` as (first_date, last_date, reason), for charts."""
        spans: list[tuple[dt.date, dt.date, str]] = []
        for k in sorted(self.frozen[env]):
            reason = self.frozen[env][k]
            if spans and spans[-1][2] == reason and self.index_on_or_after(spans[-1][1]) == k - 1:
                spans[-1] = (spans[-1][0], self.days[k], reason)
            else:
                spans.append((self.days[k], self.days[k], reason))
        return spans
