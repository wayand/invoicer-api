"""The ledger tables and the guards the database enforces on them
(docs/ledger-design.md).

The guards are triggers and constraints, so these tests go through raw SQL:
no application code stands between the statement and the database. The
balance check is deferred to the end of the transaction, so a test that
expects it to fire asks for it with SET CONSTRAINTS ALL IMMEDIATE.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models.account import Account, AccountGroup, AccountType
from app.models.ledger import (
    FiscalYear,
    JournalEntry,
    JournalLine,
    LedgerCounter,
)
from app.models.organization import Organization
from app.models.user import User


def make_chart(session, org, bank_number=6480, sales_number=1010):
    account_type = AccountType(
        organization_id=org.id,
        name="Type",
        normal_balance="debit",
        report_type="balanceSheet",
    )
    session.add(account_type)
    session.flush()
    group = AccountGroup(
        organization_id=org.id,
        account_type_id=account_type.id,
        name="Group",
        number=1,
        interval_start=1,
        interval_end=9999,
    )
    session.add(group)
    session.flush()
    accounts = {}
    for key, name, number in (
        ("bank", "Bankkonto", bank_number),
        ("sales", "Salg", sales_number),
    ):
        account = Account(
            organization_id=org.id,
            account_type_id=account_type.id,
            account_group_id=group.id,
            name=name,
            number=number,
        )
        session.add(account)
        accounts[key] = account
    session.flush()
    return accounts


@pytest.fixture
def accounts(db_session, organization):
    found = make_chart(db_session, organization)
    db_session.commit()
    return found


@pytest.fixture
def fiscal_year(db_session, organization):
    year = FiscalYear(
        organization_id=organization.id,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    db_session.add(year)
    db_session.commit()
    return year


@pytest.fixture
def ledger(db_session, organization, test_user, accounts, fiscal_year):
    """What a posting needs: the organization, user, accounts and year."""
    return {
        "org": organization,
        "user": test_user,
        "bank": accounts["bank"],
        "sales": accounts["sales"],
        "year": fiscal_year,
    }


def post_entry(session, ledger, voucher_no=1, **overrides):
    values = {
        "org": ledger["org"].id,
        "year": ledger["year"].id,
        "voucher_no": voucher_no,
        "user": ledger["user"].id,
        "reverses": None,
        "txid": None,
    }
    values.update(overrides)
    return session.execute(
        text(
            """
            INSERT INTO journal_entries
                (organization_id, fiscal_year_id, voucher_no, entry_date,
                 description, reverses_entry_id, created_by, created_at,
                 created_txid)
            VALUES (:org, :year, :voucher_no, '2026-03-01', 'Test', :reverses,
                    :user, now(), coalesce(:txid, txid_current()))
            RETURNING id
            """
        ),
        values,
    ).scalar_one()


def post_line(
    session, ledger, entry_id, line_no, account, debit=0, credit=0, **extra
):
    values = {
        "entry": entry_id,
        "org": extra.pop("org", ledger["org"].id),
        "line_no": line_no,
        "account": account.id,
        "debit": debit,
        "credit": credit,
    }
    session.execute(
        text(
            """
            INSERT INTO journal_lines
                (journal_entry_id, organization_id, line_no, account_id,
                 debit, credit)
            VALUES (:entry, :org, :line_no, :account, :debit, :credit)
            """
        ),
        values,
    )


def post_balanced(session, ledger, voucher_no=1, amount=100, **overrides):
    """A sale for cash: debit the bank, credit sales."""
    entry_id = post_entry(session, ledger, voucher_no, **overrides)
    post_line(session, ledger, entry_id, 1, ledger["bank"], debit=amount)
    post_line(session, ledger, entry_id, 2, ledger["sales"], credit=amount)
    return entry_id


def check_now(session):
    """Run the checks that are otherwise deferred to the commit."""
    session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


def refused(session, statement, message=None, **params):
    """The statement is refused by the database. The session is rolled back
    to the last commit, as the application would after the error."""
    with pytest.raises(IntegrityError) as error:
        session.execute(text(statement), params)
        check_now(session)
    session.rollback()
    if message:
        assert message in str(error.value)


# --- balance ---------------------------------------------------------------


def test_a_balanced_entry_is_accepted(db_session, ledger):
    post_balanced(db_session, ledger)

    check_now(db_session)

    sums = db_session.execute(
        text("SELECT sum(debit), sum(credit) FROM journal_lines")
    ).one()
    assert sums == (Decimal("100.00"), Decimal("100.00"))


def test_an_entry_with_several_lines_on_a_side_is_accepted(db_session, ledger):
    entry_id = post_entry(db_session, ledger)
    post_line(db_session, ledger, entry_id, 1, ledger["bank"], debit=125)
    post_line(db_session, ledger, entry_id, 2, ledger["sales"], credit=100)
    post_line(db_session, ledger, entry_id, 3, ledger["sales"], credit=25)

    check_now(db_session)


def test_an_unbalanced_entry_is_refused(db_session, ledger):
    entry_id = post_entry(db_session, ledger)
    post_line(db_session, ledger, entry_id, 1, ledger["bank"], debit=100)
    post_line(db_session, ledger, entry_id, 2, ledger["sales"], credit=99.99)

    with pytest.raises(IntegrityError) as error:
        check_now(db_session)

    assert "is not balanced" in str(error.value)


def test_an_entry_with_one_line_is_refused(db_session, ledger):
    entry_id = post_entry(db_session, ledger)
    post_line(db_session, ledger, entry_id, 1, ledger["bank"], debit=100)

    with pytest.raises(IntegrityError) as error:
        check_now(db_session)

    assert "at least 2 are required" in str(error.value)


def test_an_entry_without_lines_is_refused(db_session, ledger):
    post_entry(db_session, ledger)

    with pytest.raises(IntegrityError) as error:
        check_now(db_session)

    assert "has 0 line(s)" in str(error.value)


def test_a_line_cannot_be_debit_and_credit_at_once(db_session, ledger):
    entry_id = post_entry(db_session, ledger)

    refused(
        db_session,
        """
        INSERT INTO journal_lines (journal_entry_id, organization_id,
            line_no, account_id, debit, credit)
        VALUES (:entry, :org, 1, :account, 10, 10)
        """,
        "ck_journal_lines_one_side",
        entry=entry_id,
        org=ledger["org"].id,
        account=ledger["bank"].id,
    )


@pytest.mark.parametrize(("debit", "credit"), [(0, 0), (-5, 0), (0, -5)])
def test_a_line_must_have_one_positive_amount(
    db_session, ledger, debit, credit
):
    entry_id = post_entry(db_session, ledger)

    refused(
        db_session,
        """
        INSERT INTO journal_lines (journal_entry_id, organization_id,
            line_no, account_id, debit, credit)
        VALUES (:entry, :org, 1, :account, :debit, :credit)
        """,
        "ck_journal_lines_one_side",
        entry=entry_id,
        org=ledger["org"].id,
        account=ledger["bank"].id,
        debit=debit,
        credit=credit,
    )


def test_amounts_have_two_decimals(db_session, ledger):
    entry_id = post_entry(db_session, ledger)
    post_line(db_session, ledger, entry_id, 1, ledger["bank"], debit="0.005")
    post_line(db_session, ledger, entry_id, 2, ledger["sales"], credit="0.01")

    check_now(db_session)

    stored = db_session.execute(
        text("SELECT debit FROM journal_lines WHERE line_no = 1")
    ).scalar_one()
    assert stored == Decimal("0.01")  # rounded half up, as the money rules


# --- append only -----------------------------------------------------------


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE journal_entries SET description = 'Changed'",
        "DELETE FROM journal_entries",
        "UPDATE journal_lines SET debit = 1 WHERE debit > 0",
        "DELETE FROM journal_lines",
        "TRUNCATE journal_lines",
        "TRUNCATE journal_entries CASCADE",
    ],
)
def test_a_posted_entry_cannot_be_changed_or_deleted(
    db_session, ledger, statement
):
    post_balanced(db_session, ledger)
    check_now(db_session)  # a TRUNCATE is refused while checks are pending
    db_session.commit()

    refused(db_session, statement, "append-only")

    assert (
        db_session.execute(
            text("SELECT count(*) FROM journal_lines")
        ).scalar_one()
        == 2
    )


def test_a_line_cannot_be_added_to_an_entry_posted_earlier(db_session, ledger):
    # An entry posted in another transaction has another created_txid
    entry_id = post_entry(db_session, ledger, txid=1)

    refused(
        db_session,
        """
        INSERT INTO journal_lines (journal_entry_id, organization_id,
            line_no, account_id, debit, credit)
        VALUES (:entry, :org, 1, :account, 10, 0)
        """,
        "posted in an earlier transaction",
        entry=entry_id,
        org=ledger["org"].id,
        account=ledger["bank"].id,
    )


# --- reversals and numbers -------------------------------------------------


def test_an_entry_can_be_reversed_once(db_session, ledger):
    original = post_balanced(db_session, ledger, voucher_no=1)
    post_balanced(db_session, ledger, voucher_no=2, reverses=original)
    check_now(db_session)
    db_session.commit()

    with pytest.raises(IntegrityError) as error:
        post_balanced(db_session, ledger, voucher_no=3, reverses=original)
    db_session.rollback()

    assert "reverses_entry_id" in str(error.value)


def test_an_entry_cannot_reverse_itself(db_session, ledger):
    refused(
        db_session,
        """
        INSERT INTO journal_entries (id, organization_id, fiscal_year_id,
            voucher_no, entry_date, description, reverses_entry_id,
            created_by, created_at)
        VALUES (900, :org, :year, 1, '2026-03-01', 'Test', 900, :user, now())
        """,
        "ck_journal_entries_reverses_other",
        org=ledger["org"].id,
        year=ledger["year"].id,
        user=ledger["user"].id,
    )


def test_a_voucher_number_is_used_once_per_organization(db_session, ledger):
    post_balanced(db_session, ledger, voucher_no=1)
    db_session.commit()

    with pytest.raises(IntegrityError) as error:
        post_entry(db_session, ledger, voucher_no=1)
    db_session.rollback()

    assert "uq_journal_entries_voucher" in str(error.value)


def test_another_organization_has_its_own_numbers(db_session, ledger, country):
    post_balanced(db_session, ledger, voucher_no=1)
    other = Organization(
        name="Other ApS",
        slug="other-aps",
        country_id=country.id,
        email="other@example.com",
        logo="",
    )
    db_session.add(other)
    db_session.flush()
    other_user = User(
        organization_id=other.id,
        password_plaintext="password123",
        name="Other",
        email="other@example.com",
        otp_secret=User.generate_otp_secret(),
    )
    other_year = FiscalYear(
        organization_id=other.id,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    db_session.add_all([other_user, other_year])
    other_accounts = make_chart(db_session, other)
    db_session.commit()
    other_ledger = {
        "org": other,
        "user": other_user,
        "bank": other_accounts["bank"],
        "sales": other_accounts["sales"],
        "year": other_year,
    }

    post_balanced(db_session, other_ledger, voucher_no=1)

    check_now(db_session)


def test_a_voucher_number_starts_at_one(db_session, ledger):
    refused(
        db_session,
        """
        INSERT INTO journal_entries (organization_id, fiscal_year_id,
            voucher_no, entry_date, description, created_by, created_at)
        VALUES (:org, :year, 0, '2026-03-01', 'Test', :user, now())
        """,
        "ck_journal_entries_no",
        org=ledger["org"].id,
        year=ledger["year"].id,
        user=ledger["user"].id,
    )


def test_the_voucher_counter_starts_at_one(db_session, organization):
    db_session.add(LedgerCounter(organization_id=organization.id))
    db_session.commit()

    counter = db_session.get(LedgerCounter, organization.id)

    assert counter.next_voucher_no == 1


# --- one organization's data stays with it ---------------------------------


def second_organization(session, country):
    other = Organization(
        name="Second ApS",
        slug="second-aps",
        country_id=country.id,
        email="second@example.com",
        logo="",
    )
    session.add(other)
    session.flush()
    chart = make_chart(session, other)
    year = FiscalYear(
        organization_id=other.id,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    session.add(year)
    session.commit()
    return other, chart, year


def test_a_line_cannot_use_an_account_of_another_organization(
    db_session, ledger, country
):
    _other, chart, _year = second_organization(db_session, country)
    entry_id = post_entry(db_session, ledger)

    refused(
        db_session,
        """
        INSERT INTO journal_lines (journal_entry_id, organization_id,
            line_no, account_id, debit, credit)
        VALUES (:entry, :org, 1, :account, 10, 0)
        """,
        "fk_journal_lines_account_org",
        entry=entry_id,
        org=ledger["org"].id,
        account=chart["bank"].id,
    )


def test_an_entry_cannot_use_a_fiscal_year_of_another_organization(
    db_session, ledger, country
):
    _other, _chart, year = second_organization(db_session, country)

    refused(
        db_session,
        """
        INSERT INTO journal_entries (organization_id, fiscal_year_id,
            voucher_no, entry_date, description, created_by, created_at)
        VALUES (:org, :year, 1, '2026-03-01', 'Test', :user, now())
        """,
        "fk_journal_entries_fiscal_year_org",
        org=ledger["org"].id,
        year=year.id,
        user=ledger["user"].id,
    )


def test_an_account_with_postings_cannot_be_deleted(db_session, ledger):
    post_balanced(db_session, ledger)
    db_session.commit()

    refused(
        db_session,
        "DELETE FROM accounts WHERE id = :id",
        "fk_journal_lines_account_org",
        id=ledger["bank"].id,
    )


def test_an_account_with_postings_can_be_renamed(db_session, ledger):
    post_balanced(db_session, ledger)
    db_session.commit()

    ledger["bank"].name = "Driftskonto"
    ledger["bank"].number = 6485
    db_session.commit()

    line = db_session.query(JournalLine).filter_by(line_no=1).one()
    assert line.account.name == "Driftskonto"
    assert line.account.number == 6485


# --- accounts --------------------------------------------------------------


def test_the_key_of_an_account_is_its_id(app):
    from sqlalchemy import inspect

    from app.models.base import db

    key = inspect(db.engine).get_pk_constraint("accounts")

    assert key["constrained_columns"] == ["id"]


def add_account(session, org_id, name, number):
    group = session.query(AccountGroup).filter_by(organization_id=org_id).one()
    session.add(
        Account(
            organization_id=org_id,
            account_type_id=group.account_type_id,
            account_group_id=group.id,
            name=name,
            number=number,
        )
    )


def test_an_account_number_is_used_once_per_organization(
    db_session, organization, accounts
):
    add_account(db_session, organization.id, "Another name", 6480)
    with pytest.raises(IntegrityError) as error:
        db_session.flush()
    db_session.rollback()

    assert "uq_accounts_org_number" in str(error.value)


def test_an_account_name_is_used_once_per_organization(
    db_session, organization, accounts
):
    add_account(db_session, organization.id, "Bankkonto", 6999)
    with pytest.raises(IntegrityError) as error:
        db_session.flush()
    db_session.rollback()

    assert "uq_accounts_org_name" in str(error.value)


def test_a_system_role_has_one_account_per_organization(db_session, accounts):
    accounts["bank"].system_role = "bank"
    db_session.commit()

    accounts["sales"].system_role = "bank"
    with pytest.raises(IntegrityError) as error:
        db_session.flush()
    db_session.rollback()

    assert "uq_accounts_org_system_role" in str(error.value)


def test_the_same_system_role_can_be_held_in_another_organization(
    db_session, accounts, country
):
    accounts["bank"].system_role = "bank"
    db_session.commit()
    _other, chart, _year = second_organization(db_session, country)

    chart["bank"].system_role = "bank"
    db_session.commit()

    assert chart["bank"].system_role == "bank"


def test_an_unknown_system_role_is_refused(db_session, accounts):
    accounts["bank"].system_role = "treasure"
    with pytest.raises(IntegrityError) as error:
        db_session.flush()
    db_session.rollback()

    assert "ck_accounts_system_role" in str(error.value)


def test_an_account_has_no_role_and_no_standard_account_by_default(accounts):
    assert accounts["bank"].system_role is None
    assert accounts["bank"].standard_account is None


# --- fiscal years and the company form -------------------------------------


def test_a_fiscal_year_starts_open(fiscal_year):
    assert fiscal_year.status == "open"


def test_a_fiscal_year_cannot_end_before_it_starts(db_session, organization):
    db_session.add(
        FiscalYear(
            organization_id=organization.id,
            start_date=date(2026, 12, 31),
            end_date=date(2026, 1, 1),
        )
    )
    with pytest.raises(IntegrityError) as error:
        db_session.flush()
    db_session.rollback()

    assert "ck_fiscal_years_dates" in str(error.value)


def test_a_fiscal_year_status_is_open_or_closed(db_session, fiscal_year):
    fiscal_year.status = "archived"
    with pytest.raises(IntegrityError) as error:
        db_session.flush()
    db_session.rollback()

    assert "ck_fiscal_years_status" in str(error.value)


def test_two_fiscal_years_cannot_start_on_the_same_day(
    db_session, organization, fiscal_year
):
    db_session.add(
        FiscalYear(
            organization_id=organization.id,
            start_date=fiscal_year.start_date,
            end_date=date(2026, 6, 30),
        )
    )
    with pytest.raises(IntegrityError) as error:
        db_session.flush()
    db_session.rollback()

    assert "uq_fiscal_years_org_start" in str(error.value)


def test_a_new_organization_is_a_sole_proprietorship(organization):
    assert organization.company_form == "enkeltmandsvirksomhed"


def test_an_organization_can_be_an_aps(db_session, organization):
    organization.company_form = "aps"
    db_session.commit()

    assert organization.company_form == "aps"


def test_an_unknown_company_form_is_refused(db_session, organization):
    organization.company_form = "foundation"
    with pytest.raises(IntegrityError) as error:
        db_session.flush()
    db_session.rollback()

    assert "ck_organizations_company_form" in str(error.value)


# --- the models ------------------------------------------------------------


def test_an_entry_is_read_with_its_lines_in_order(db_session, ledger):
    post_balanced(db_session, ledger, amount=250)
    check_now(db_session)
    db_session.commit()

    entry = db_session.query(JournalEntry).one()

    assert [(line.line_no, line.account.number) for line in entry.lines] == [
        (1, 6480),
        (2, 1010),
    ]
    assert entry.lines[0].debit == Decimal("250.00")
    assert entry.lines[1].credit == Decimal("250.00")
