"""Our classification of the official VAT codes (app/vat.py)."""

from collections import Counter
from decimal import Decimal

import pytest

from app import vat
from app.chart import STARTER_ACCOUNTS
from app.standard_chart import standard_vat_codes
from app.vat import (
    ACQUISITION_GOODS,
    ACQUISITION_SERVICES,
    DEFERRED,
    DEFERRED_REASONS,
    INPUT,
    NO_VAT,
    OUTPUT,
    PURCHASES,
    SALES,
    SUPPORTED,
    percent,
    vat_code_rows,
)

D = Decimal
ROWS = {row["code"]: row for row in vat_code_rows()}
SUPPORTED_ROWS = [row for row in ROWS.values() if row["is_supported"]]


@pytest.mark.parametrize(
    "text, expected",
    [
        ("25%", D("0.25")),
        ("0%", D("0")),
        ("100%", D("1")),
        ("5%", D("0.05")),
        ("66,6%", D("0.666")),
        ("33,3%", D("0.333")),
        (" 50% ", D("0.5")),
        ("", None),
        ("x%", None),
        ("Skøn", None),
        ("Delvis", None),
        ("Arealfordeling", None),
        ("Maks 25% af særligt fradrags-grundlag", None),
    ],
)
def test_a_share_in_the_list_is_a_fraction_or_nothing(text, expected):
    assert percent(text) == expected


def test_every_official_code_is_classified_once():
    codes = {code.new_code for code in standard_vat_codes()}

    assert len(codes) == 72
    assert set(SUPPORTED) | set(DEFERRED) == codes
    assert not set(SUPPORTED) & set(DEFERRED)
    assert [row["code"] for row in vat_code_rows()] == [
        code.new_code for code in standard_vat_codes()
    ]


def test_22_codes_are_supported_and_50_deferred():
    assert len(SUPPORTED) == 22
    assert len(DEFERRED) == 50
    assert Counter(DEFERRED.values()) == {
        "variable_deduction": 23,
        "special_scheme": 10,
        "oss": 5,
        "fixed_share_unconfirmed": 5,
        "domestic_reverse_charge": 2,
        "refund_scheme": 2,
        "import_vat": 2,
        "triangular_trade": 1,
    }
    assert set(DEFERRED.values()) == set(DEFERRED_REASONS)


def test_an_unclassified_code_is_an_error(monkeypatch):
    monkeypatch.setattr(
        vat, "SUPPORTED", {k: v for k, v in SUPPORTED.items() if k != "S01"}
    )

    with pytest.raises(ValueError, match="S01 is not classified"):
        vat_code_rows()


def test_a_code_cannot_be_both_supported_and_deferred(monkeypatch):
    monkeypatch.setattr(vat, "DEFERRED", {**DEFERRED, "S01": "oss"})

    with pytest.raises(ValueError, match="Supported and deferred"):
        vat_code_rows()


def test_a_classified_code_that_is_not_in_the_list_is_an_error(monkeypatch):
    monkeypatch.setattr(vat, "DEFERRED", {**DEFERRED, "S99": "oss"})

    with pytest.raises(ValueError, match="S99"):
        vat_code_rows()


def test_a_code_has_both_of_its_names():
    assert ROWS["S01"]["legacy_code"] == "S1"
    assert ROWS["K210"]["legacy_code"] == "K-EU-V-1"
    assert ROWS["K460"]["legacy_code"] == "K-%EU-Y-1"
    assert len({row["legacy_code"] for row in ROWS.values()}) == 72


def test_every_code_is_valid_from_the_date_of_the_list():
    assert {row["valid_from"] for row in ROWS.values()} == {"2025-12-01"}


def test_the_oss_codes_are_sales_and_the_rest_follow_the_group():
    assert Counter(row["applies_to"] for row in ROWS.values()) == {
        SALES: 23,
        PURCHASES: 49,
    }
    assert all(
        ROWS[code]["applies_to"] == SALES
        for code in SUPPORTED
        if code[0] == "S"
    )
    assert all(
        ROWS[code]["applies_to"] == PURCHASES
        for code in SUPPORTED
        if code[0] == "K"
    )


def test_a_deferred_code_is_not_classified():
    for code in DEFERRED:
        row = ROWS[code]
        assert not row["is_supported"]
        assert row["direction"] is None and row["base_box"] is None
        assert row["deferred_reason"] == DEFERRED[code]


def test_a_supported_code_has_a_direction_and_no_reason():
    for row in SUPPORTED_ROWS:
        assert row["direction"] is not None
        assert row["deferred_reason"] is None


@pytest.mark.parametrize("row", SUPPORTED_ROWS, ids=lambda row: row["code"])
def test_a_supported_code_is_consistent(row):
    if row["applies_to"] == SALES:
        assert row["direction"] in (OUTPUT, NO_VAT)
        assert row["deduction"] is None
        assert row["base_box"] in (None, "b_goods", "b_services", "c")
    else:
        assert row["direction"] in (
            INPUT,
            ACQUISITION_GOODS,
            ACQUISITION_SERVICES,
            NO_VAT,
        )
        assert row["deduction"] is not None
        assert row["base_box"] in (None, "a_goods", "a_services")
    # VAT is calculated from a rate, so a code that posts VAT has one
    if row["direction"] != NO_VAT:
        assert row["rate"] == D("0.25") or row["code"] == "S01"
    # Rubrik A is for acquisitions from the EU, so only those have it
    assert (row["base_box"] or "").startswith("a_") == (
        row["code"] in ("K210", "K230", "K260", "K280")
    )


def test_what_the_rate_and_the_deduction_of_some_codes_are():
    assert (ROWS["S01"]["rate"], ROWS["S01"]["deduction"]) == (D("0.25"), None)
    assert (ROWS["K010"]["rate"], ROWS["K010"]["deduction"]) == (
        D("0.25"),
        D("1"),
    )
    assert ROWS["K070"]["deduction"] == D("0.25")
    assert ROWS["K040"]["deduction"] == D("0.5")
    assert ROWS["K030"]["rate"] is None and ROWS["K030"]["deduction"] == D("0")
    assert ROWS["S21"]["rate"] == D("0")
    assert ROWS["S81"]["rate"] is None


def test_where_the_net_amount_is_reported():
    boxes = {
        code: row["base_box"] for code, row in ROWS.items() if row["base_box"]
    }
    assert boxes == {
        "S02": "c",
        "S21": "b_goods",
        "S22": "b_goods",
        "S23": "b_services",
        "S41": "c",
        "S42": "c",
        "K210": "a_goods",
        "K230": "a_goods",
        "K260": "a_services",
        "K280": "a_services",
    }


def test_the_starter_accounts_start_with_a_supported_code_of_the_right_kind():
    with_code = [item for item in STARTER_ACCOUNTS if item.vat]

    assert len(with_code) == 22
    for item in with_code:
        row = ROWS[item.vat]
        assert row["is_supported"], item.number
        expected = SALES if item.type == "Income" else PURCHASES
        assert item.type in ("Income", "Expense"), item.number
        assert row["applies_to"] == expected, item.number
