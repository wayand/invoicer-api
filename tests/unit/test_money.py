import json
from decimal import Decimal
from pathlib import Path

import pytest
from marshmallow import Schema

from app.money import (
    MAX_AMOUNT,
    DecimalNumber,
    MoneyError,
    invoice_totals,
    line_amount,
    round_money,
)

CASES = json.loads((Path(__file__).parent / "money_cases.json").read_text())[
    "cases"
]


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_invoice_totals_follow_the_rules(case):
    lines = [(Decimal(qty), Decimal(price)) for qty, price in case["lines"]]

    totals = invoice_totals(lines, Decimal(case["rate"]))

    assert [str(amount) for amount in totals.lines] == case["line_amounts"]
    assert str(totals.amount) == case["amount"]
    assert str(totals.vat_amount) == case["vat_amount"]
    assert str(totals.gross_amount) == case["gross_amount"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0.004", "0.00"),
        ("0.005", "0.01"),
        ("1.005", "1.01"),
        ("2.675", "2.68"),
        ("-0.005", "-0.01"),
        ("-2.675", "-2.68"),
        ("10", "10.00"),
    ],
)
def test_round_money_rounds_half_up_away_from_zero(value, expected):
    assert str(round_money(Decimal(value))) == expected


def test_a_line_amount_is_exact_before_it_is_rounded():
    # In floating point 3 x 0.335 is 1.0050000000000001 and 1.005 x 100 is
    # 100.49999999999999: Decimal has neither problem
    assert line_amount(Decimal("3"), Decimal("0.335")) == Decimal("1.01")


def test_the_largest_amount_that_fits_is_accepted():
    totals = invoice_totals([(Decimal("1"), MAX_AMOUNT)], Decimal("0"))

    assert totals.amount == MAX_AMOUNT


@pytest.mark.parametrize(
    "lines",
    [
        [(Decimal("1"), MAX_AMOUNT + Decimal("0.01"))],
        [(Decimal("99999999999"), Decimal("99999999999"))],
        # The net fits, but the net plus VAT does not
        [(Decimal("1"), Decimal("900000000000"))],
    ],
)
def test_an_amount_that_cannot_be_stored_is_refused(lines):
    with pytest.raises(MoneyError):
        invoice_totals(lines, Decimal("0.25"))


class SampleSchema(Schema):
    price = DecimalNumber(places=3)
    amount = DecimalNumber(places=2)


def test_decimal_number_is_written_as_a_json_number():
    dumped = SampleSchema().dump(
        {"price": Decimal("0.125"), "amount": Decimal("1250.50")}
    )

    assert dumped == {"price": 0.125, "amount": 1250.5}
    assert isinstance(dumped["amount"], float)


def test_decimal_number_keeps_negative_values():
    dumped = SampleSchema().dump(
        {"price": Decimal("-1.5"), "amount": Decimal("-2.68")}
    )

    assert dumped == {"price": -1.5, "amount": -2.68}


def test_decimal_number_reads_with_half_up_rounding():
    loaded = SampleSchema().load({"price": "1.0005", "amount": "2.675"})

    assert loaded == {"price": Decimal("1.001"), "amount": Decimal("2.68")}
