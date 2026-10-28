"""The starter chart (app/chart.py) against the standard it is taken from."""

from collections import defaultdict

import pytest

from app.chart import (
    ACCOUNT_TYPES,
    APS,
    SOLE_PROPRIETORSHIP,
    STARTER_ACCOUNTS,
    group_interval,
    group_of,
    standard_number,
    starter_accounts,
)
from app.models.account import SYSTEM_ROLES
from app.standard_chart import ACCOUNT, standard_accounts

OWN = [item for item in STARTER_ACCOUNTS if item.name]
STANDARD = [item for item in STARTER_ACCOUNTS if not item.name]

SOLE_ONLY_ROLES = {"owner_capital", "owner_withdrawals", "owner_deposits"}
SOLE_ONLY_ROLES.add("annual_result")
APS_ONLY_ROLES = {"share_capital", "retained_earnings"}


def roles(company_form):
    return [item.role for item in starter_accounts(company_form) if item.role]


def test_a_starter_number_is_used_once():
    numbers = [item.number for item in STARTER_ACCOUNTS]

    assert len(numbers) == len(set(numbers))


@pytest.mark.parametrize("item", STANDARD, ids=lambda item: item.number)
def test_a_standard_starter_account_is_an_account_of_the_standard(item):
    found = standard_accounts()[item.number]

    assert found.kind == ACCOUNT
    assert found.group is not None


@pytest.mark.parametrize("item", OWN, ids=lambda item: item.number)
def test_our_own_account_is_free_and_maps_to_an_account_of_the_standard(item):
    standard = standard_accounts()

    assert item.number not in standard
    assert standard[item.standard_account].kind == ACCOUNT
    assert group_of(item) == standard[item.standard_account].group


@pytest.mark.parametrize("item", STARTER_ACCOUNTS, ids=lambda item: item.number)
def test_the_type_fits_the_numbers_of_the_standard(item):
    number = standard_number(item)
    ranges = {
        "Income": (1000, 3999),
        "Expense": (1000, 3999),
        "Asset": (5000, 6499),
        "Equity": (6500, 6999),
        "Liability": (7000, 8999),
    }

    low, high = ranges[item.type]
    assert low <= number <= high
    assert item.type in ACCOUNT_TYPES


def test_every_account_of_a_standard_group_has_the_same_type():
    types = defaultdict(set)
    for item in STARTER_ACCOUNTS:
        types[group_of(item)].add(item.type)

    assert {
        group: kinds for group, kinds in types.items() if len(kinds) > 1
    } == {}


def test_every_role_has_an_account_and_none_is_used_twice():
    assert set(roles(SOLE_PROPRIETORSHIP)) | set(roles(APS)) == set(
        SYSTEM_ROLES
    )
    for form in (SOLE_PROPRIETORSHIP, APS):
        assert len(roles(form)) == len(set(roles(form)))


def test_a_sole_proprietorship_has_the_owner_accounts_and_no_share_capital():
    found = set(roles(SOLE_PROPRIETORSHIP))

    assert SOLE_ONLY_ROLES <= found
    assert not APS_ONLY_ROLES & found


def test_an_aps_has_share_capital_and_no_owner_accounts():
    found = set(roles(APS))

    assert APS_ONLY_ROLES <= found
    assert not SOLE_ONLY_ROLES & found


def test_both_forms_have_the_roles_that_posting_needs():
    common = set(SYSTEM_ROLES) - SOLE_ONLY_ROLES - APS_ONLY_ROLES

    assert common <= set(roles(SOLE_PROPRIETORSHIP))
    assert common <= set(roles(APS))


def test_an_unknown_company_form_has_no_chart():
    with pytest.raises(ValueError, match="Unknown company form"):
        starter_accounts("foundation")


def test_a_group_runs_up_to_the_next_heading():
    # 1001 Nettoomsætning, then 1400 Ændring i lagre af færdigvarer
    assert group_interval(1001) == (1001, 1399)
