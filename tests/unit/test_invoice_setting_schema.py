"""
The reminder fee is a Decimal in the database and a number in the JSON. A fee
of 0 is a real value, so it has to come back as 0, not as null: the form shows
null as an empty field and refuses to save it.
"""

from decimal import Decimal

import pytest

from app.models.invoice_setting_schema import invoice_setting_schema


def dumped_fee(value):
    return invoice_setting_schema.dump({"default_reminder_fee": value})[
        "default_reminder_fee"
    ]


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        (Decimal("0"), 0.0),
        (Decimal("0.00"), 0.0),
        (Decimal("50"), 50.0),
        (Decimal("12.50"), 12.5),
    ],
)
def test_dump_returns_the_fee_as_a_number(stored, expected):
    fee = dumped_fee(stored)

    assert fee == expected
    assert isinstance(fee, float)


def test_dump_returns_null_when_there_is_no_fee():
    assert dumped_fee(None) is None
