"""Working-day calendar: weekends, bank holidays, freezes, prod windows and CAB."""

import datetime as dt

import pytest

from fleetwave.models import Env
from fleetwave.scheduler.calendar import WorkCalendar

D = dt.date


def idx(cal: WorkCalendar, d: dt.date) -> int:
    return cal.index_on_or_after(d)


def test_weekends_and_bank_holidays_excluded(cal: WorkCalendar) -> None:
    assert all(d.weekday() < 5 for d in cal.days)
    assert D(2027, 3, 26) not in cal.days  # Good Friday
    assert D(2027, 3, 29) not in cal.days  # Easter Monday
    assert cal.date(0) == D(2027, 1, 4)


def test_index_on_or_after_rolls_forward(cal: WorkCalendar) -> None:
    assert cal.date(idx(cal, D(2027, 1, 9))) == D(2027, 1, 11)  # Saturday -> Monday


def test_index_beyond_horizon(cal: WorkCalendar) -> None:
    with pytest.raises(ValueError, match="horizon"):
        cal.index_on_or_after(D(2035, 1, 1))


def test_month_end_freeze_last_three_working_days(cal: WorkCalendar) -> None:
    for d in (D(2027, 1, 27), D(2027, 1, 28), D(2027, 1, 29)):
        assert cal.frozen[Env.PROD][idx(cal, d)] == "month-end"
        assert not cal.is_frozen(idx(cal, d), Env.DEV)
    # March 2027: 26th and 29th are bank holidays, so the last 3 working days are 25, 30, 31.
    for d in (D(2027, 3, 25), D(2027, 3, 30), D(2027, 3, 31)):
        assert cal.is_frozen(idx(cal, d), Env.PROD)


def test_payday_window_rolls_back_from_weekend(cal: WorkCalendar) -> None:
    # 25 April 2027 is a Sunday -> payday Friday 23rd; window = Thu 22, Fri 23, Mon 26.
    for d in (D(2027, 4, 22), D(2027, 4, 23), D(2027, 4, 26)):
        assert cal.frozen[Env.PROD][idx(cal, d)] == "payday"
    assert not cal.is_frozen(idx(cal, D(2027, 4, 21)), Env.PROD)


def test_peak_freeze_scoped_to_preprod_and_prod(cal: WorkCalendar) -> None:
    k = idx(cal, D(2027, 4, 6))
    assert cal.is_frozen(k, Env.PROD)
    assert cal.is_frozen(k, Env.PREPROD)
    assert not cal.is_frozen(k, Env.TEST)


def test_prod_days_are_tue_to_thu(cal: WorkCalendar) -> None:
    assert cal.is_prod_day(idx(cal, D(2027, 2, 2)))  # Tue
    assert cal.is_prod_day(idx(cal, D(2027, 2, 4)))  # Thu
    assert not cal.is_prod_day(idx(cal, D(2027, 2, 1)))  # Mon
    assert not cal.is_prod_day(idx(cal, D(2027, 2, 5)))  # Fri


def test_can_run(cal: WorkCalendar) -> None:
    tue = idx(cal, D(2027, 2, 2))
    assert cal.can_run(Env.PROD, tue, 2)  # Tue-Wed
    assert not cal.can_run(Env.PROD, tue + 1, 3)  # Wed-Fri
    assert cal.can_run(Env.DEV, tue + 3, 2)  # Fri-Mon is fine outside prod
    assert not cal.can_run(Env.DEV, cal.horizon - 1, 2)


def test_cab_is_thursday_and_approval_precedes_prod(cal: WorkCalendar) -> None:
    assert all(cal.date(c).weekday() == 3 for c in cal.cab_days)
    mon = idx(cal, D(2027, 2, 1))
    assert cal.first_cab_on_or_after(mon) == idx(cal, D(2027, 2, 4))
    assert cal.date(cal.earliest_prod_start(mon)) == D(2027, 2, 5)  # day after CAB
    thu = idx(cal, D(2027, 2, 4))
    assert cal.earliest_prod_start(thu) == thu + 1  # evidence ready on CAB day still counts


def test_week_and_calendar_days(cal: WorkCalendar) -> None:
    assert cal.week(0) == 0
    assert cal.week(idx(cal, D(2027, 1, 11))) == 1
    assert cal.calendar_days(1) == 1
    assert cal.calendar_days(idx(cal, D(2027, 1, 11)) + 1) == 8


def test_freeze_ranges_merge_contiguous_days(cal: WorkCalendar) -> None:
    spans = cal.freeze_ranges(Env.PREPROD)
    assert spans == [(D(2027, 3, 30), D(2027, 4, 9), "tax-year-end peak")]
