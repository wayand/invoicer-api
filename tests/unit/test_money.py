import json
import random
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
from app.vat_engine import NetLine, Rule, vat_lines

_FILE = json.loads((Path(__file__).parent / "money_cases.json").read_text())
CASES = _FILE["cases"]
CODED_CASES = _FILE["coded_cases"]
RATES = {code: Decimal(rate) for code, rate in _FILE["rates"].items()}


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_invoice_totals_follow_the_rules(case):
    lines = [
        (Decimal(qty), Decimal(price), "S") for qty, price in case["lines"]
    ]

    totals = invoice_totals(lines, {"S": Decimal(case["rate"])})

    assert [str(amount) for amount in totals.lines] == case["line_amounts"]
    assert str(totals.amount) == case["amount"]
    assert str(totals.vat_amount) == case["vat_amount"]
    assert str(totals.gross_amount) == case["gross_amount"]


@pytest.mark.parametrize(
    "case", CODED_CASES, ids=[case["name"] for case in CODED_CASES]
)
def test_invoice_totals_are_worked_out_per_vat_code(case):
    lines = [
        (Decimal(qty), Decimal(price), code)
        for qty, price, code in case["lines"]
    ]

    totals = invoice_totals(lines, RATES)

    assert [str(amount) for amount in totals.lines] == case["line_amounts"]
    assert str(totals.amount) == case["amount"]
    assert str(totals.vat_amount) == case["vat_amount"]
    assert str(totals.gross_amount) == case["gross_amount"]
    assert [
        [item.code, str(item.base), str(item.vat)] for item in totals.by_code
    ] == case["by_code"]
    assert all(item.rate == RATES[item.code] for item in totals.by_code)


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
    totals = invoice_totals(
        [(Decimal("1"), MAX_AMOUNT, "S")], {"S": Decimal("0")}
    )

    assert totals.amount == MAX_AMOUNT


@pytest.mark.parametrize(
    "lines",
    [
        [(Decimal("1"), MAX_AMOUNT + Decimal("0.01"), "S")],
        [(Decimal("99999999999"), Decimal("99999999999"), "S")],
        # The net fits, but the net plus VAT does not
        [(Decimal("1"), Decimal("900000000000"), "S")],
        # Every line and the net fit, but the base of one code does not
        [
            (Decimal("1"), Decimal("900000000000"), "T"),
            (Decimal("1"), Decimal("900000000000"), "T"),
            (Decimal("1"), Decimal("-900000000000"), "U"),
        ],
    ],
)
def test_an_amount_that_cannot_be_stored_is_refused(lines):
    with pytest.raises(MoneyError):
        invoice_totals(
            lines,
            {"S": Decimal("0.25"), "T": Decimal("0"), "U": Decimal("0")},
        )


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


@pytest.mark.parametrize("seed", range(100))
def test_an_invoice_has_the_vat_the_engine_posts_for_it(seed):
    # An invoice is posted with the engine in phase 3: the VAT per code on the
    # invoice must be the VAT of the lines the engine adds
    rng = random.Random(seed)
    rates = {"S01": Decimal("0.25"), "S02": Decimal("0"), "T": Decimal("0.07")}
    lines = [
        (
            Decimal(rng.randint(-5000, 5000)) / 1000,
            Decimal(rng.randint(-300000, 300000)) / 1000,
            rng.choice(list(rates)),
        )
        for _ in range(rng.randint(1, 8))
    ]

    totals = invoice_totals(lines, rates)

    net_lines = []
    for amount, (_qty, _price, code) in zip(totals.lines, lines):
        rule = Rule(code, "sales", rates[code], None, "output")
        net_lines.append(
            NetLine(
                1,
                abs(amount) if amount < 0 else Decimal("0.00"),
                amount if amount > 0 else Decimal("0.00"),
                rule,
            )
        )
    posted = {
        item.code: item.credit - item.debit for item in vat_lines(net_lines)
    }
    assert {
        item.code: item.vat for item in totals.by_code if item.vat
    } == posted
