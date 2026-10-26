"""The two official files in app/seed/standard and the loader for them."""

import hashlib
import re
from pathlib import Path

import pytest

from app.standard_chart import (
    ACCOUNT,
    CHART_FILE,
    GROUP,
    HEADING,
    SUM,
    VAT_CODES_FILE,
    standard_accounts,
    standard_vat_codes,
)

DOCS = Path(__file__).parents[2] / "docs"

# SOURCE.md in the same folder says the same
CHART_SHA256 = (
    "ad5b9ba73856c29e5d4a81e2a89751efce86c5d69fa705f693a79204d6f55f97"
)
VAT_CODES_SHA256 = (
    "2c6e42779ab5fa60e32d2c6e27ddc643dda038216154f1cb764580f1924e90d9"
)

# Our own account, which is not in the standard (docs/chart-of-accounts.md)
OWN_ACCOUNTS = {6481}

SOME_ACCOUNTS = {
    1010: "Salg af varer og ydelser",
    1710: "Ydelseskøb udland, EU",
    6190: "Tilgodehavender fra salg og tjenesteydelser",
    6330: "Øvrige tilgodehavender (omsætningsaktiv)",
    6480: "Bankkonto",
    6916: "Årets resultat (kun klasse A)",
    6923: "Privat hævet (kun klasse A)",
    7680: "Salgsmoms",
    7740: "Købsmoms",
    7840: "Skyldig moms",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_the_chart_file_is_the_one_that_was_downloaded():
    assert sha256(CHART_FILE) == CHART_SHA256


def test_the_vat_code_file_is_the_one_that_was_downloaded():
    assert sha256(VAT_CODES_FILE) == VAT_CODES_SHA256


def test_the_chart_has_all_its_accounts():
    accounts = standard_accounts().values()

    assert sum(1 for item in accounts if item.kind != SUM) == 603
    assert sum(1 for item in accounts if item.kind == SUM) == 119


def test_every_number_has_four_digits():
    assert all(1000 <= number <= 9999 for number in standard_accounts())


@pytest.mark.parametrize(("number", "name"), SOME_ACCOUNTS.items())
def test_a_known_account_has_its_number_and_name(number, name):
    found = standard_accounts()[number]

    assert found.name == name
    assert found.kind == ACCOUNT


def test_an_account_knows_its_group():
    assert standard_accounts()[1010].group == 1001
    assert standard_accounts()[1001].kind == GROUP
    assert standard_accounts()[1000].kind == HEADING


def test_sum_accounts_are_marked_as_sums():
    # 4999 is the total "Årets resultat": an account to read, not to post to
    assert standard_accounts()[4999].kind == SUM
    assert standard_accounts()[7450].kind == SUM


def test_our_own_account_numbers_are_free():
    assert not OWN_ACCOUNTS & set(standard_accounts())


def test_the_vat_code_list_has_72_codes():
    codes = standard_vat_codes()

    assert len(codes) == 72
    assert sum(1 for item in codes if item.code.startswith("S")) == 23
    assert sum(1 for item in codes if item.code.startswith("K")) == 49


def test_a_vat_code_has_an_old_and_a_new_name():
    by_code = {item.code: item for item in standard_vat_codes()}

    assert by_code["K1"].new_code == "K010"
    assert by_code["K-EU-Y-1"].new_code == "K260"
    assert by_code["K-EU-Y-1"].vat_return.startswith("Rubrik A - ydelser")
    assert by_code["S1"].rate == "25%"


def test_vat_codes_are_unique():
    codes = [item.code for item in standard_vat_codes()]

    assert len(codes) == len(set(codes))


def test_the_chart_document_agrees_with_the_standard():
    """Every account in the tables of docs/chart-of-accounts.md exists in the
    standard with that name, except our own accounts."""
    text = (DOCS / "chart-of-accounts.md").read_text(encoding="utf-8")
    rows = re.findall(r"^\| (\d{4}) \| ([^|]+?) \|", text, flags=re.MULTILINE)
    standard = standard_accounts()

    assert len(rows) > 40
    for number, name in rows:
        if int(number) in OWN_ACCOUNTS:
            continue
        assert int(number) in standard, number
        assert standard[int(number)].name == name, number
