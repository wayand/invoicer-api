"""When a VAT period starts and ends, and when its return is due
(app/vat_periods.py, docs/vat-design.md, section 8)."""

import random
from datetime import date, timedelta

import pytest

from app.vat_periods import due_date, next_weekday, period_bounds


@pytest.mark.parametrize(
    ("period_type", "day", "start", "end"),
    [
        ("month", date(2026, 2, 17), date(2026, 2, 1), date(2026, 2, 28)),
        ("month", date(2028, 2, 1), date(2028, 2, 1), date(2028, 2, 29)),
        ("month", date(2026, 12, 31), date(2026, 12, 1), date(2026, 12, 31)),
        ("quarter", date(2026, 1, 1), date(2026, 1, 1), date(2026, 3, 31)),
        ("quarter", date(2026, 3, 31), date(2026, 1, 1), date(2026, 3, 31)),
        ("quarter", date(2026, 4, 1), date(2026, 4, 1), date(2026, 6, 30)),
        ("quarter", date(2026, 8, 15), date(2026, 7, 1), date(2026, 9, 30)),
        ("quarter", date(2026, 12, 31), date(2026, 10, 1), date(2026, 12, 31)),
        ("half_year", date(2026, 3, 9), date(2026, 1, 1), date(2026, 6, 30)),
        ("half_year", date(2026, 6, 30), date(2026, 1, 1), date(2026, 6, 30)),
        ("half_year", date(2026, 7, 1), date(2026, 7, 1), date(2026, 12, 31)),
    ],
)
def test_a_period_runs_from_the_first_to_the_last_day_of_its_calendar_part(
    period_type, day, start, end
):
    assert period_bounds(period_type, day) == (start, end)


@pytest.mark.parametrize(
    ("period_type", "end", "due"),
    [
        # The first day of the third month after the period ends
        ("quarter", date(2026, 3, 31), date(2026, 6, 1)),
        ("quarter", date(2026, 6, 30), date(2026, 9, 1)),
        ("quarter", date(2026, 9, 30), date(2026, 12, 1)),
        # 1 March 2026 is a Sunday: the date is 2 March, as it was that year
        ("quarter", date(2025, 12, 31), date(2026, 3, 2)),
        ("half_year", date(2026, 6, 30), date(2026, 9, 1)),
        ("half_year", date(2025, 12, 31), date(2026, 3, 2)),
        # The 25th of the next month, moved past a weekend
        ("month", date(2026, 1, 31), date(2026, 2, 25)),
        ("month", date(2025, 12, 31), date(2026, 1, 26)),
        ("month", date(2026, 11, 30), date(2026, 12, 25)),
    ],
)
def test_the_due_date_follows_the_rule_for_the_period_type(
    period_type, end, due
):
    assert due_date(period_type, end) == due


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2026, 6, 1), date(2026, 6, 1)),  # a Monday
        (date(2026, 9, 5), date(2026, 9, 7)),  # a Saturday
        (date(2026, 9, 6), date(2026, 9, 7)),  # a Sunday
        (date(2026, 9, 4), date(2026, 9, 4)),  # a Friday
    ],
)
def test_a_weekend_moves_to_the_monday(day, expected):
    assert next_weekday(day) == expected


@pytest.mark.parametrize("seed", range(100))
def test_periods_follow_each_other_without_gaps_and_are_due_on_a_weekday(seed):
    generator = random.Random(seed)
    period_type = generator.choice(["month", "quarter", "half_year"])
    day = date(2020, 1, 1) + timedelta(days=generator.randint(0, 3000))

    start, end = period_bounds(period_type, day)
    next_start, next_end = period_bounds(period_type, end + timedelta(days=1))

    assert start <= day <= end
    assert next_start == end + timedelta(days=1)
    assert next_end > end
    # The same boundaries from any day inside the period
    assert period_bounds(period_type, start) == (start, end)
    assert period_bounds(period_type, end) == (start, end)
    due = due_date(period_type, end)
    assert due > end
    assert due.weekday() < 5


def test_a_change_of_type_works_from_the_next_period_on():
    # A settled quarter ends on 31 March. The next period starts on 1 April
    # and runs to the next boundary of the type there is then
    start = date(2026, 4, 1)

    assert period_bounds("month", start)[1] == date(2026, 4, 30)
    assert period_bounds("quarter", start)[1] == date(2026, 6, 30)
    assert period_bounds("half_year", start)[1] == date(2026, 6, 30)
    # From the middle of a boundary the period is shorter than the type
    assert period_bounds("half_year", date(2026, 8, 1))[1] == date(2026, 12, 31)
