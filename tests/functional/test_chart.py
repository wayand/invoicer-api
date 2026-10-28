"""Giving an organization the starter chart of accounts (app/chart.py) and
the commands that do it."""

import json
from pathlib import Path

import pytest

from app import cli
from app.chart import (
    ACCOUNT_TYPES,
    APS,
    SOLE_PROPRIETORSHIP,
    apply_starter_chart,
    group_interval,
    starter_accounts,
)
from app.models.account import Account, AccountGroup, AccountType
from app.models.organization import Organization
from app.standard_chart import standard_accounts

SEED_DIR = Path(__file__).parents[2] / "app" / "seed" / "orgs"


def accounts_of(org):
    return {
        item.number: item
        for item in Account.query.filter_by(organization_id=org.id)
    }


def make_org(db_session, country, slug="org-a", form=SOLE_PROPRIETORSHIP):
    org = Organization(
        name=f"{slug} ApS",
        slug=slug,
        country_id=country.id,
        email=f"{slug}@example.com",
        logo="",
        company_form=form,
    )
    db_session.add(org)
    db_session.commit()
    return org


def test_a_sole_proprietorship_gets_its_starter_accounts(
    db_session, organization
):
    result = apply_starter_chart(organization)

    expected = {item.number for item in starter_accounts(SOLE_PROPRIETORSHIP)}
    assert set(accounts_of(organization)) == expected
    assert set(result.created) == expected
    assert not result.adopted and not result.skipped


def test_an_aps_gets_the_equity_accounts_of_a_company(db_session, country):
    org = make_org(db_session, country, "aps-org", APS)

    apply_starter_chart(org)

    found = accounts_of(org)
    assert {6510, 6940} <= set(found)
    assert not {6916, 6923} & set(found)


def test_an_account_has_the_name_and_standard_account_of_the_standard(
    organization,
):
    apply_starter_chart(organization)
    standard = standard_accounts()

    for number, account in accounts_of(organization).items():
        if number == 6481:
            continue
        assert account.name == standard[number].name
        assert account.standard_account == number


def test_the_skattekonto_is_our_own_account_mapped_to_6330(organization):
    apply_starter_chart(organization)

    skattekonto = accounts_of(organization)[6481]

    assert skattekonto.name == "Skattekonto"
    assert skattekonto.standard_account == 6330
    assert skattekonto.system_role == "tax_account"
    assert skattekonto.account_type.name == "Asset"
    assert skattekonto.account_group.number == 6301


def test_the_accounts_hold_the_roles_the_posting_service_needs(organization):
    apply_starter_chart(organization)

    roles = {
        item.system_role: item.number
        for item in accounts_of(organization).values()
        if item.system_role
    }

    assert roles["receivables"] == 6190
    assert roles["bank"] == 6480
    assert roles["output_vat"] == 7680
    assert roles["input_vat"] == 7740
    assert roles["vat_payable"] == 7840
    assert roles["annual_result"] == 6916
    assert roles["owner_withdrawals"] == 6923


def test_the_bank_account_can_receive_payments(organization):
    apply_starter_chart(organization)

    bank = accounts_of(organization)[6480]

    assert bank.is_bank_account and bank.is_payment_enabled and bank.is_deposit
    assert not accounts_of(organization)[1010].is_deposit


def test_the_types_are_the_ones_the_app_expects(organization):
    apply_starter_chart(organization)

    types = {
        item.name: (item.normal_balance, item.report_type)
        for item in AccountType.query.filter_by(organization_id=organization.id)
    }

    assert types == ACCOUNT_TYPES
    assert accounts_of(organization)[1010].account_type.name == "Income"
    assert accounts_of(organization)[7680].account_type.name == "Liability"


def test_the_groups_are_the_groups_of_the_standard(organization):
    apply_starter_chart(organization)

    sales = accounts_of(organization)[1010].account_group

    assert (sales.number, sales.name) == (1001, "Nettoomsætning")
    assert (sales.interval_start, sales.interval_end) == group_interval(1001)
    assert (
        sales.account_type_id == accounts_of(organization)[1010].account_type_id
    )
    groups = AccountGroup.query.filter_by(organization_id=organization.id).all()
    assert len({(item.number, item.name) for item in groups}) == len(groups)


def test_applying_the_chart_twice_changes_nothing(db_session, organization):
    first = apply_starter_chart(organization)
    count = Account.query.filter_by(organization_id=organization.id).count()

    second = apply_starter_chart(organization)

    assert not second.created and not second.adopted and not second.skipped
    assert set(second.unchanged) == set(first.created)
    assert (
        Account.query.filter_by(organization_id=organization.id).count()
        == count
    )


def test_an_account_with_the_number_is_kept_and_gets_its_role(
    db_session, organization
):
    first = apply_starter_chart(organization)
    assert first.created
    bank = accounts_of(organization)[6480]
    bank.name = "Min bank"
    bank.system_role = None
    bank.standard_account = None
    db_session.commit()

    result = apply_starter_chart(organization)

    assert result.adopted == [6480]
    bank = accounts_of(organization)[6480]
    assert (bank.name, bank.system_role, bank.standard_account) == (
        "Min bank",
        "bank",
        6480,
    )


def test_an_account_that_uses_the_name_is_not_replaced(
    db_session, organization
):
    other = make_account(
        db_session, organization, 9000, "Salg af varer og ydelser"
    )

    result = apply_starter_chart(organization)

    assert "already used" in result.skipped[1010]
    assert 1010 not in accounts_of(organization)
    assert other.number == 9000


def test_a_role_held_by_another_account_is_not_given_twice(
    db_session, organization
):
    make_account(db_session, organization, 9001, "Old bank", role="bank")

    result = apply_starter_chart(organization)

    assert "held by account 9001" in result.skipped[6480]
    assert 6480 not in accounts_of(organization)


def test_one_organizations_chart_does_not_touch_another(
    db_session, organization, country
):
    other = make_org(db_session, country, "other-org")
    apply_starter_chart(organization)
    apply_starter_chart(other)

    assert set(accounts_of(organization)) == set(accounts_of(other))
    assert not {item.id for item in accounts_of(organization).values()} & {
        item.id for item in accounts_of(other).values()
    }


def make_account(session, org, number, name, role=None):
    type_ = AccountType(
        organization_id=org.id,
        name=f"Type {number}",
        normal_balance="debit",
        report_type="balanceSheet",
    )
    session.add(type_)
    session.flush()
    group = AccountGroup(
        organization_id=org.id,
        account_type_id=type_.id,
        name=f"Group {number}",
        number=number,
        interval_start=number,
        interval_end=number,
    )
    session.add(group)
    session.flush()
    account = Account(
        organization_id=org.id,
        account_type_id=type_.id,
        account_group_id=group.id,
        name=name,
        number=number,
        system_role=role,
    )
    session.add(account)
    session.commit()
    return account


# --- the command -----------------------------------------------------------


@pytest.fixture(autouse=True)
def commands(app):
    cli.register_commands(app)


def test_the_command_applies_the_chart(runner, db_session, organization):
    result = runner.invoke(args=["chart-apply", organization.slug])

    assert result.exit_code == 0, result.output
    assert "Demo ApS (enkeltmandsvirksomhed)" in result.output
    assert (
        f"{len(starter_accounts(SOLE_PROPRIETORSHIP))} created" in result.output
    )
    assert 6480 in accounts_of(organization)


def test_the_command_can_be_run_again(runner, db_session, organization):
    runner.invoke(args=["chart-apply", organization.slug])

    result = runner.invoke(args=["chart-apply", organization.slug])

    assert result.exit_code == 0, result.output
    assert "0 created" in result.output
    assert "already there" in result.output


def test_the_command_reports_what_it_skipped(runner, db_session, organization):
    make_account(db_session, organization, 9001, "Old bank", role="bank")

    result = runner.invoke(args=["chart-apply", organization.slug])

    assert "skipped 6480: role bank is held by account 9001" in result.output


def test_the_command_rejects_an_unknown_organization(runner, db_session):
    result = runner.invoke(args=["chart-apply", "nobody"])

    assert result.exit_code != 0
    assert "No organization with slug nobody" in result.output


# --- the seed files --------------------------------------------------------


def test_the_demo_seed_describes_the_organization_and_its_bank():
    data = json.loads((SEED_DIR / "demo.json").read_text(encoding="utf-8"))

    assert "account_types" not in data  # the chart is created by the code
    for key in ("users", "products", "contacts", "tax_rates"):
        data.pop(key)
    bank = data.pop("bank_account")
    organization = Organization(**data)

    assert organization.company_form in (SOLE_PROPRIETORSHIP, APS)
    for key in bank:
        assert hasattr(Account, key), key
