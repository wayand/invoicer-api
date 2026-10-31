"""The VAT engine (app/vat_engine.py), on the cases it shares with the app."""

import json
import random
from decimal import Decimal
from pathlib import Path

import pytest

from app.money import round_money
from app.vat import vat_code_rows
from app.vat_engine import (
    INPUT_VAT,
    NONDEDUCTIBLE,
    OUTPUT_VAT,
    VAT,
    VAT_ACCOUNT_ROLES,
    NetLine,
    Rule,
    allocate,
    vat_lines,
)

D = Decimal
CASES = json.loads((Path(__file__).parent / "vat_cases.json").read_text())
OFFICIAL = {row["code"]: row for row in vat_code_rows()}


def rule(code: str, rules=CASES["rules"]) -> Rule:
    given = rules[code]
    return Rule(
        code=code,
        applies_to=given["applies_to"],
        rate=None if given["rate"] is None else D(given["rate"]),
        deduction=None if given["deduction"] is None else D(given["deduction"]),
        direction=given["direction"],
    )


def net_lines(lines) -> list[NetLine]:
    return [
        NetLine(
            account_id=line["account"],
            debit=D(line["debit"]),
            credit=D(line["credit"]),
            rule=rule(line["code"]),
        )
        for line in lines
    ]


def as_json(posted) -> list[dict]:
    return [
        {
            "part": item.part,
            "code": item.code,
            "role": item.role,
            "account": item.account_id,
            "debit": str(item.debit),
            "credit": str(item.credit),
        }
        for item in posted
    ]


@pytest.mark.parametrize("case", CASES["cases"], ids=lambda case: case["name"])
def test_the_shared_cases(case):
    assert as_json(vat_lines(net_lines(case["lines"]))) == case["vat_lines"]


@pytest.mark.parametrize("code", CASES["rules"])
def test_the_rules_of_the_cases_are_the_official_ones(code):
    """The cases are copied to the app: they must not drift from the list."""
    official = OFFICIAL[code]
    given = CASES["rules"][code]

    assert given["applies_to"] == official["applies_to"]
    assert given["direction"] == official["direction"]
    assert (None if official["rate"] is None else str(official["rate"])) == (
        given["rate"]
    )
    assert (
        None if official["deduction"] is None else str(official["deduction"])
    ) == given["deduction"]


def test_every_direction_and_a_credit_note_of_each_is_in_the_cases():
    directions = {CASES["rules"][c]["direction"] for c in CASES["rules"]}
    assert directions == {
        "output",
        "input",
        "acquisition_goods",
        "acquisition_services",
        "none",
    }
    credit_notes = [
        case for case in CASES["cases"] if "credit note" in case["name"]
    ]
    assert len(credit_notes) >= 4


def test_no_lines_have_no_vat():
    assert vat_lines([]) == []


# --- sharing an amount -----------------------------------------------------


@pytest.mark.parametrize(
    "total, weights, expected",
    [
        ("0.04", ["0.10", "0.10", "0.10"], ["0.02", "0.01", "0.01"]),
        ("56.25", ["100", "200"], ["18.75", "37.50"]),
        ("0.01", ["1", "1"], ["0.01", "0.00"]),
        ("10.00", ["3", "3", "3"], ["3.34", "3.33", "3.33"]),
        # The share of a negative amount is the positive one, negated
        ("-0.04", ["0.10", "0.10", "0.10"], ["-0.02", "-0.01", "-0.01"]),
        ("-0.04", ["-0.10", "-0.10", "-0.10"], ["-0.02", "-0.01", "-0.01"]),
        ("5.00", ["0", "0"], ["0.00", "0.00"]),
        ("0.00", ["1", "2"], ["0.00", "0.00"]),
    ],
)
def test_an_amount_is_shared_in_proportion_to_the_cent(
    total, weights, expected
):
    shares = allocate(D(total), [D(weight) for weight in weights])

    assert [str(share) for share in shares] == expected


@pytest.mark.parametrize("seed", range(200))
def test_the_shares_always_add_up_to_the_amount(seed):
    generator = random.Random(seed)
    count = generator.randint(1, 7)
    weights = [D(generator.randint(1, 100000)) / 100 for _ in range(count)]
    total = D(generator.randint(-100000, 100000)) / 100

    shares = allocate(total, weights)

    assert sum(shares) == total
    assert all(share.as_tuple().exponent == -2 for share in shares)
    # Nobody is more than a cent away from the exact share
    exact = [total * weight / sum(weights) for weight in weights]
    assert all(
        abs(share - part) < D("0.01") for share, part in zip(shares, exact)
    )


# --- the whole of an entry, on random data --------------------------------

SALES_CODES = ["S01", "S02", "S21", "S23", "S81"]
PURCHASE_CODES = ["K010", "K030", "K040", "K070", "K210", "K230", "K260"]
PURCHASE_CODES += ["K280", "K460", "K480"]
RULES = {
    row["code"]: Rule(
        code=row["code"],
        applies_to=row["applies_to"],
        rate=row["rate"],
        deduction=row["deduction"],
        direction=row["direction"],
    )
    for row in vat_code_rows()
    if row["is_supported"]
}


def random_lines(generator) -> list[NetLine]:
    lines = []
    for _ in range(generator.randint(1, 8)):
        code = generator.choice(SALES_CODES + PURCHASE_CODES)
        amount = D(generator.randint(1, 5_000_000)) / 100
        # Most lines are sales (credits) and costs (debits); some are credit
        # notes, on the other side
        side = generator.choice(["normal", "normal", "normal", "other"])
        sales = RULES[code].applies_to == "sales"
        debit_side = sales == (side == "other")
        lines.append(
            NetLine(
                account_id=generator.randint(1, 4),
                debit=amount if debit_side else D("0.00"),
                credit=D("0.00") if debit_side else amount,
                rule=RULES[code],
            )
        )
    return lines


def signed_net(line: NetLine) -> Decimal:
    return line.net


@pytest.mark.parametrize("seed", range(300))
def test_the_vat_of_an_entry_is_what_the_rules_say(seed):
    lines = random_lines(random.Random(seed))
    posted = vat_lines(lines)

    for code in dict.fromkeys(line.rule.code for line in lines):
        group = [line for line in lines if line.rule.code == code]
        rule = group[0].rule
        base = sum((line.net for line in group), D("0.00"))
        mine = [item for item in posted if item.code == code]
        if rule.direction == "none" or rule.rate is None:
            assert mine == []
            continue
        vat = round_money(base * rule.rate)
        by_role = lambda role: sum(  # noqa: E731
            (
                item.debit - item.credit
                for item in mine
                if item.part == VAT and item.role == role
            ),
            D("0.00"),
        )
        nondeductible = sum(
            (
                item.debit - item.credit
                for item in mine
                if item.part == NONDEDUCTIBLE
            ),
            D("0.00"),
        )
        if rule.direction == "output":
            # Sales: the VAT is a credit
            assert -by_role(OUTPUT_VAT) == vat
            assert nondeductible == 0
        else:
            deductible = round_money(vat * rule.deduction)
            assert by_role(INPUT_VAT) == deductible
            assert nondeductible == vat - deductible
            if rule.direction == "input":
                assert by_role(INPUT_VAT) + nondeductible == vat
            else:
                # Acquisition VAT is a credit of the whole VAT, and what is
                # deducted or costs is a debit of the same: nothing is owed
                # or paid to the supplier
                role = (
                    "vat_eu_goods"
                    if rule.direction == "acquisition_goods"
                    else "vat_eu_services"
                )
                assert -by_role(role) == vat
                assert by_role(INPUT_VAT) + nondeductible + by_role(role) == 0


@pytest.mark.parametrize("seed", range(100))
def test_a_line_the_engine_adds_is_one_side_and_on_a_known_account(seed):
    lines = random_lines(random.Random(seed))
    accounts = {line.account_id for line in lines}

    for item in vat_lines(lines):
        assert (item.debit > 0) != (item.credit > 0)
        assert item.part in (VAT, NONDEDUCTIBLE)
        if item.part == VAT:
            assert item.role in VAT_ACCOUNT_ROLES and item.account_id is None
        else:
            assert item.role is None and item.account_id in accounts


def test_a_purchase_and_its_credit_note_cancel_out():
    cost = NetLine(1, D("800.00"), D("0.00"), rule("K010"))
    credit = NetLine(1, D("0.00"), D("800.00"), rule("K010"))

    assert vat_lines([cost, credit]) == []
