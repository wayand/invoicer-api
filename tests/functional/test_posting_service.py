"""The posting service (app/ledger.py): what gets into the journal, and what
is refused before the database sees it."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

import app.ledger as ledger_module
from app.chart import apply_starter_chart
from app.ledger import (
    LedgerConflict,
    LedgerError,
    LedgerNotFound,
    LineInput,
    close_fiscal_year,
    fiscal_year_for,
    post_entry,
    reverse_entry,
)
from app.models.account import Account
from app.models.contact import Contact
from app.models.country import Country
from app.models.ledger import (
    FiscalYear,
    JournalEntry,
    JournalLine,
    LedgerCounter,
)
from app.models.organization import Organization
from app.models.user import User

D = Decimal


@pytest.fixture
def books(db_session, organization, test_user):
    apply_starter_chart(organization)
    accounts = {
        item.number: item
        for item in Account.query.filter_by(organization_id=organization.id)
    }
    return {
        "org": organization,
        "user": test_user,
        "bank": accounts[6480],
        "sales": accounts[1010],
        "vat": accounts[7680],
        "receivables": accounts[6190],
        "accounts": accounts,
    }


def sale(books, amount="100.00", **kwargs):
    """Bank debited, sales credited: the simplest balanced entry."""
    return [
        LineInput(account_id=books["bank"].id, debit=D(amount)),
        LineInput(account_id=books["sales"].id, credit=D(amount)),
    ]


def post(books, day=date(2026, 3, 1), lines=None, description="A sale", **kw):
    return post_entry(
        books["org"].id,
        books["user"].id,
        day,
        description,
        lines if lines is not None else sale(books),
        **kw,
    )


def entries(books):
    return JournalEntry.query.filter_by(organization_id=books["org"].id)


# --- posting ---------------------------------------------------------------


def test_a_balanced_entry_is_posted_with_voucher_number_one(db_session, books):
    entry = post(books)

    assert entry.voucher_no == 1
    assert entry.entry_date == date(2026, 3, 1)
    assert entry.description == "A sale"
    assert entry.source_type == "manual"
    assert entry.created_by == books["user"].id
    assert [
        (line.line_no, line.account_id, line.debit, line.credit)
        for line in entry.lines
    ] == [
        (1, books["bank"].id, D("100.00"), D("0.00")),
        (2, books["sales"].id, D("0.00"), D("100.00")),
    ]


def test_voucher_numbers_run_on_without_gaps_or_restarts(db_session, books):
    numbers = [
        post(books, date(2026, 12, 31)).voucher_no,
        post(books, date(2027, 1, 1)).voucher_no,  # a new fiscal year
        post(books, date(2026, 6, 1)).voucher_no,  # back in the first year
    ]

    assert numbers == [1, 2, 3]


def test_the_calendar_year_is_opened_by_the_first_posting_in_it(
    db_session, books
):
    entry = post(books, date(2026, 3, 1))

    year = db_session.get(FiscalYear, entry.fiscal_year_id)
    assert (year.start_date, year.end_date) == (
        date(2026, 1, 1),
        date(2026, 12, 31),
    )
    assert year.status == "open"


def test_a_fiscal_year_is_opened_once(db_session, books):
    first = post(books, date(2026, 1, 1))
    second = post(books, date(2026, 12, 31))

    assert first.fiscal_year_id == second.fiscal_year_id
    assert (
        FiscalYear.query.filter_by(organization_id=books["org"].id).count() == 1
    )


def test_an_existing_fiscal_year_that_covers_the_date_is_used(
    db_session, books
):
    broken = FiscalYear(
        organization_id=books["org"].id,
        start_date=date(2026, 7, 1),
        end_date=date(2027, 6, 30),
    )
    db_session.add(broken)
    db_session.commit()

    entry = post(books, date(2027, 2, 1))

    assert entry.fiscal_year_id == broken.id
    assert (
        FiscalYear.query.filter_by(organization_id=books["org"].id).count() == 1
    )


def test_no_calendar_year_is_opened_over_another_fiscal_year(db_session, books):
    db_session.add(
        FiscalYear(
            organization_id=books["org"].id,
            start_date=date(2026, 7, 1),
            end_date=date(2027, 6, 30),
        )
    )
    db_session.commit()

    with pytest.raises(LedgerConflict, match="would overlap"):
        post(books, date(2026, 3, 1))

    assert entries(books).count() == 0


def test_nothing_can_be_posted_in_a_closed_fiscal_year(db_session, books):
    first = post(books, date(2026, 3, 1))
    close_fiscal_year(books["org"].id, first.fiscal_year_id)

    with pytest.raises(LedgerConflict, match="is closed"):
        post(books, date(2026, 4, 1))

    assert entries(books).count() == 1
    assert db_session.get(LedgerCounter, books["org"].id).next_voucher_no == 2


def test_another_year_is_still_open_when_one_is_closed(db_session, books):
    first = post(books, date(2026, 3, 1))
    close_fiscal_year(books["org"].id, first.fiscal_year_id)

    assert post(books, date(2027, 3, 1)).voucher_no == 2


@pytest.mark.parametrize("day", [date(1999, 12, 31), date(2101, 1, 1)])
def test_a_date_that_is_a_typing_mistake_is_refused(db_session, books, day):
    with pytest.raises(LedgerError, match="The date must be in 2000 to 2100"):
        post(books, day)

    assert (
        FiscalYear.query.filter_by(organization_id=books["org"].id).count() == 0
    )


def test_another_organization_has_its_own_voucher_numbers_and_years(
    db_session, books, country
):
    post(books)
    other = Organization(
        name="Other ApS",
        slug="other-aps",
        country_id=country.id,
        email="other@example.com",
        logo="",
    )
    db_session.add(other)
    db_session.flush()
    user = User(
        organization_id=other.id,
        password_plaintext="password123",
        name="Other",
        email="other@example.com",
        otp_secret=User.generate_otp_secret(),
    )
    db_session.add(user)
    db_session.commit()
    apply_starter_chart(other)
    mine = {
        item.number: item
        for item in Account.query.filter_by(organization_id=other.id)
    }

    entry = post_entry(
        other.id,
        user.id,
        date(2026, 3, 1),
        "Theirs",
        [
            LineInput(account_id=mine[6480].id, debit=D("5")),
            LineInput(account_id=mine[1010].id, credit=D("5")),
        ],
    )

    assert entry.voucher_no == 1
    assert entry.fiscal_year_id != post(books).fiscal_year_id


# --- what is refused -------------------------------------------------------


def test_an_unbalanced_entry_is_refused(db_session, books):
    lines = [
        LineInput(account_id=books["bank"].id, debit=D("100")),
        LineInput(account_id=books["sales"].id, credit=D("99.99")),
    ]

    with pytest.raises(
        LedgerError, match="does not balance: debit 100.00, credit 99.99"
    ):
        post(books, lines=lines)

    assert entries(books).count() == 0
    assert db_session.get(LedgerCounter, books["org"].id) is None


def test_an_entry_with_one_line_is_refused(db_session, books):
    with pytest.raises(LedgerError, match="at least 2 lines"):
        post(books, lines=sale(books)[:1])


def test_an_entry_with_too_many_lines_is_refused(db_session, books):
    lines = [
        LineInput(account_id=books["bank"].id, debit=D("1")),
        LineInput(account_id=books["sales"].id, credit=D("1")),
    ] * 251

    with pytest.raises(LedgerError, match="at most 500 lines"):
        post(books, lines=lines)


@pytest.mark.parametrize(
    ("debit", "credit"),
    [("10", "10"), ("0", "0"), ("0.004", "0")],
    ids=["both", "neither", "rounds to nothing"],
)
def test_a_line_is_either_a_debit_or_a_credit(db_session, books, debit, credit):
    lines = [
        LineInput(
            account_id=books["bank"].id, debit=D(debit), credit=D(credit)
        ),
        LineInput(account_id=books["sales"].id, credit=D("10")),
    ]

    with pytest.raises(LedgerError, match="Line 1: needs either a debit"):
        post(books, lines=lines)


def test_a_negative_amount_is_refused(db_session, books):
    lines = [
        LineInput(account_id=books["bank"].id, debit=D("-10")),
        LineInput(account_id=books["sales"].id, credit=D("10")),
    ]

    with pytest.raises(LedgerError, match="cannot be negative"):
        post(books, lines=lines)


def test_an_amount_too_large_to_store_is_refused(db_session, books):
    huge = D("1000000000000")
    lines = [
        LineInput(account_id=books["bank"].id, debit=huge),
        LineInput(account_id=books["sales"].id, credit=huge),
    ]

    with pytest.raises(LedgerError, match="too large"):
        post(books, lines=lines)


def test_amounts_are_rounded_half_up_as_the_money_rules_say(db_session, books):
    lines = [
        LineInput(account_id=books["bank"].id, debit=D("10.005")),
        LineInput(account_id=books["sales"].id, credit=D("10.01")),
    ]

    entry = post(books, lines=lines)

    assert entry.lines[0].debit == D("10.01")


def test_rounding_can_leave_an_entry_unbalanced_and_it_is_refused(
    db_session, books
):
    # 0.005 + 0.005 rounds to 0.01 + 0.01, against a credit of 0.01
    lines = [
        LineInput(account_id=books["bank"].id, debit=D("0.005")),
        LineInput(account_id=books["receivables"].id, debit=D("0.005")),
        LineInput(account_id=books["sales"].id, credit=D("0.01")),
    ]

    with pytest.raises(LedgerError, match="does not balance"):
        post(books, lines=lines)


def test_an_unknown_account_is_refused(db_session, books):
    lines = [
        LineInput(account_id=999999, debit=D("10")),
        LineInput(account_id=books["sales"].id, credit=D("10")),
    ]

    with pytest.raises(LedgerError, match="no account with id 999999"):
        post(books, lines=lines)


def test_an_account_of_another_organization_looks_unknown(
    db_session, books, country
):
    other = Organization(
        name="Other ApS",
        slug="other-aps",
        country_id=country.id,
        email="other@example.com",
        logo="",
    )
    db_session.add(other)
    db_session.commit()
    apply_starter_chart(other)
    theirs = Account.query.filter_by(
        organization_id=other.id, number=6480
    ).one()
    lines = [
        LineInput(account_id=theirs.id, debit=D("10")),
        LineInput(account_id=books["sales"].id, credit=D("10")),
    ]

    with pytest.raises(LedgerError, match=f"no account with id {theirs.id}"):
        post(books, lines=lines)


def test_an_archived_account_is_refused(db_session, books):
    books["bank"].is_archived = True
    db_session.commit()

    with pytest.raises(LedgerError, match="account 6480 Bankkonto is archived"):
        post(books)


def test_a_line_can_be_for_a_contact_of_the_organization(db_session, books):
    contact = Contact(
        organization_id=books["org"].id,
        name="Client",
        email="client@example.com",
        country_id=db_session.query(Country).first().id,
    )
    db_session.add(contact)
    db_session.commit()
    lines = [
        LineInput(
            account_id=books["receivables"].id,
            debit=D("125"),
            contact_id=contact.id,
        ),
        LineInput(account_id=books["sales"].id, credit=D("100")),
        LineInput(account_id=books["vat"].id, credit=D("25")),
    ]

    entry = post(books, lines=lines)

    assert entry.lines[0].contact_id == contact.id


def test_a_contact_of_another_organization_is_refused(
    db_session, books, country
):
    other = Organization(
        name="Other ApS",
        slug="other-aps",
        country_id=country.id,
        email="other@example.com",
        logo="",
    )
    db_session.add(other)
    db_session.flush()
    contact = Contact(
        organization_id=other.id,
        name="Their client",
        email="their@example.com",
        country_id=country.id,
    )
    db_session.add(contact)
    db_session.commit()
    lines = sale(books)
    lines[0] = LineInput(
        account_id=books["bank"].id, debit=D("100"), contact_id=contact.id
    )

    with pytest.raises(LedgerError, match="no contact with id"):
        post(books, lines=lines)


@pytest.mark.parametrize("description", ["", "   ", None])
def test_a_description_is_required(db_session, books, description):
    with pytest.raises(LedgerError, match="The description is required"):
        post(books, description=description)


def test_a_description_is_trimmed_and_limited(db_session, books):
    assert post(books, description="  A sale  ").description == "A sale"
    with pytest.raises(LedgerError, match="longer than 255"):
        post(books, description="x" * 256)


# --- nothing is half done --------------------------------------------------


def test_a_failure_while_posting_gives_the_voucher_number_back(
    db_session, books, monkeypatch
):
    assert post(books).voucher_no == 1
    real_line = ledger_module.JournalLine

    def failing(**kwargs):
        raise RuntimeError("the disk is full")

    monkeypatch.setattr(ledger_module, "JournalLine", failing)
    with pytest.raises(RuntimeError):
        post(books)
    monkeypatch.setattr(ledger_module, "JournalLine", real_line)

    assert post(books).voucher_no == 2
    assert entries(books).count() == 2


def test_the_database_refuses_an_unbalanced_entry_that_got_past_the_checks(
    db_session, books, monkeypatch
):
    """If the checks above had a bug, the triggers still hold."""
    monkeypatch.setattr(
        ledger_module,
        "_check_lines",
        lambda lines: [
            LineInput(account_id=books["bank"].id, debit=D("100.00")),
            LineInput(account_id=books["sales"].id, credit=D("90.00")),
        ],
    )

    with pytest.raises(IntegrityError, match="is not balanced"):
        post(books)
    monkeypatch.undo()

    assert entries(books).count() == 0
    assert post(books).voucher_no == 1


# --- reversals -------------------------------------------------------------


def test_a_reversal_is_the_opposite_entry(db_session, books):
    original = post(books, lines=sale(books, "250.00"))

    reversal = reverse_entry(
        books["org"].id,
        books["user"].id,
        original.id,
        entry_date=date(2026, 4, 1),
    )

    assert reversal.voucher_no == 2
    assert reversal.entry_date == date(2026, 4, 1)
    assert reversal.reverses_entry_id == original.id
    assert (reversal.source_type, reversal.source_id) == (
        "reversal",
        original.id,
    )
    assert reversal.description == "Reversal of voucher 1: A sale"
    assert [
        (line.account_id, line.debit, line.credit) for line in reversal.lines
    ] == [
        (books["bank"].id, D("0.00"), D("250.00")),
        (books["sales"].id, D("250.00"), D("0.00")),
    ]


def test_an_entry_and_its_reversal_cancel_out(db_session, books):
    original = post(books)
    reverse_entry(books["org"].id, books["user"].id, original.id)

    net = {}
    for line in JournalLine.query.filter_by(organization_id=books["org"].id):
        net[line.account_id] = net.get(line.account_id, D("0")) + (
            line.debit - line.credit
        )

    assert set(net.values()) == {D("0")}


def test_a_reversal_can_have_its_own_description_and_is_dated_today(
    db_session, books
):
    original = post(books)

    reversal = reverse_entry(
        books["org"].id,
        books["user"].id,
        original.id,
        description="Posted on the wrong account",
    )

    assert reversal.description == "Posted on the wrong account"
    assert reversal.entry_date == date.today()


def test_an_entry_is_reversed_once(db_session, books):
    original = post(books)
    reverse_entry(books["org"].id, books["user"].id, original.id)

    with pytest.raises(LedgerConflict, match="already reversed by voucher 2"):
        reverse_entry(books["org"].id, books["user"].id, original.id)

    assert entries(books).count() == 2


def test_a_reversal_is_not_reversed(db_session, books):
    original = post(books)
    reversal = reverse_entry(books["org"].id, books["user"].id, original.id)

    with pytest.raises(LedgerConflict, match="is a reversal"):
        reverse_entry(books["org"].id, books["user"].id, reversal.id)


def test_an_unknown_entry_cannot_be_reversed(db_session, books):
    with pytest.raises(LedgerNotFound):
        reverse_entry(books["org"].id, books["user"].id, 999999)


def test_an_entry_of_another_organization_cannot_be_reversed(
    db_session, books, country
):
    original = post(books)
    other = Organization(
        name="Other ApS",
        slug="other-aps",
        country_id=country.id,
        email="other@example.com",
        logo="",
    )
    db_session.add(other)
    db_session.commit()

    with pytest.raises(LedgerNotFound):
        reverse_entry(other.id, books["user"].id, original.id)


def test_a_reversal_is_refused_in_a_closed_fiscal_year(db_session, books):
    original = post(books, date(2026, 3, 1))
    close_fiscal_year(books["org"].id, original.fiscal_year_id)

    with pytest.raises(LedgerConflict, match="is closed"):
        reverse_entry(
            books["org"].id,
            books["user"].id,
            original.id,
            entry_date=date(2026, 6, 1),
        )

    assert not JournalEntry.query.filter_by(
        reverses_entry_id=original.id
    ).count()


# --- fiscal years ----------------------------------------------------------


def test_a_fiscal_year_is_closed_once(db_session, books):
    year = fiscal_year_for(books["org"].id, date(2026, 3, 1))

    close_fiscal_year(books["org"].id, year.id)

    assert year.status == "closed"
    with pytest.raises(LedgerConflict, match="already closed"):
        close_fiscal_year(books["org"].id, year.id)


def test_an_unknown_fiscal_year_cannot_be_closed(db_session, books):
    with pytest.raises(LedgerNotFound):
        close_fiscal_year(books["org"].id, 999999)
