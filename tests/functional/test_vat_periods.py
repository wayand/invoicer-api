"""VAT periods: settling a period, locking it, and filing it
(app/vat_periods.py, docs/vat-design.md, section 8)."""

import random
from datetime import date, timedelta
from decimal import Decimal

import pytest
from flask_jwt_extended import create_access_token

from app.chart import apply_starter_chart
from app.ledger import (
    LedgerConflict,
    LedgerError,
    LineInput,
    post_entry,
    reverse_entry,
)
from app.models.account import Account
from app.models.audit import AuditLog
from app.models.ledger import FiscalYear, JournalEntry, LedgerCounter
from app.models.organization import Organization
from app.models.user import User
from app.models.vat_period import VatPeriod
from app.reports import trial_balance, vat_report
from app.vat_periods import (
    change_due_date,
    file_period,
    open_period,
    settle_period,
)
from tests.functional.test_vat_report import random_entry

D = Decimal
# The first quarter of 2026 is over, and the fourth quarter of 2099 is not
LATER = date(2026, 11, 1)


def money(value) -> Decimal:
    return D(str(value))


def headers(user) -> dict:
    token = create_access_token(
        identity=user.email, additional_claims={"tv": user.token_version}
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def books(db_session, organization, test_user):
    organization.vat_period_type = "quarter"
    db_session.commit()
    apply_starter_chart(organization)
    accounts = {
        item.number: item
        for item in Account.query.filter_by(organization_id=organization.id)
    }
    return {
        "org": organization,
        "user": test_user,
        "headers": headers(test_user),
        "accounts": accounts,
    }


def line(books, number, code=None, **amount):
    return LineInput(
        account_id=books["accounts"][number].id,
        debit=D(amount.get("debit", "0")),
        credit=D(amount.get("credit", "0")),
        vat_code=code,
    )


def post(books, day, lines, description="Entry"):
    return post_entry(
        books["org"].id, books["user"].id, day, description, lines
    )


def settle(books, today=LATER):
    return settle_period(books["org"].id, books["user"].id, today)


def sale(books, day, net="1000"):
    gross = D(net) * D("1.25")
    return post(
        books,
        day,
        [line(books, 6480, debit=gross), line(books, 1010, "S01", credit=net)],
        "Sale",
    )


def purchase(books, day, net="800"):
    gross = D(net) * D("1.25")
    return post(
        books,
        day,
        [
            line(books, 1610, "K010", debit=net),
            line(books, 7440, credit=gross),
        ],
        "Purchase",
    )


@pytest.fixture
def worked(db_session, books):
    """The first quarter of 2026: sales VAT 250, input VAT 406.25 and
    acquisition VAT 200 + 200, so 243.75 is to be paid."""
    sale(books, date(2026, 1, 10))
    post(
        books,
        date(2026, 2, 1),
        [
            line(books, 6480, debit="400"),
            line(books, 1150, "S23", credit="400"),
        ],
    )
    purchase(books, date(2026, 2, 10))
    post(
        books,
        date(2026, 2, 20),
        [
            line(books, 1910, "K070", debit="100"),
            line(books, 7440, credit="125"),
        ],
    )
    post(
        books,
        date(2026, 3, 5),
        [
            line(books, 1710, "K260", debit="800"),
            line(books, 7440, credit="800"),
        ],
    )
    post(
        books,
        date(2026, 3, 6),
        [
            line(books, 1630, "K230", debit="800"),
            line(books, 7440, credit="800"),
        ],
    )


def shown(books, entry):
    numbers = {a.id: n for n, a in books["accounts"].items()}
    return [
        (numbers[item.account_id], item.debit, item.credit)
        for item in entry.lines
    ]


def balances(books, up_to=None):
    report = trial_balance(books["org"].id, None, up_to)
    return {
        item["number"]: item["closing_balance"] for item in report["accounts"]
    }


def count(model, books):
    return model.query.filter_by(organization_id=books["org"].id).count()


# --- the open period -------------------------------------------------------


def test_an_organization_that_is_not_registered_has_no_period(
    db_session, books
):
    books["org"].vat_period_type = None
    db_session.commit()

    assert open_period(books["org"].id) is None


def test_nothing_is_open_before_a_posting_has_a_vat_code(db_session, books):
    post(
        books,
        date(2026, 2, 10),
        [line(books, 6480, debit="10"), line(books, 1010, credit="10")],
    )

    assert open_period(books["org"].id) is None


def test_the_first_period_starts_with_the_calendar_part_of_the_first_code(
    db_session, books
):
    sale(books, date(2026, 5, 20))
    sale(books, date(2026, 2, 10))

    period = open_period(books["org"].id)

    # The earliest posting decides: the first quarter
    assert period.start_date == date(2026, 1, 1)
    assert period.due_date == date(2026, 6, 1)
    assert period.period_type == "quarter"


def test_a_month_organization_has_monthly_periods(db_session, books):
    books["org"].vat_period_type = "month"
    db_session.commit()
    sale(books, date(2026, 2, 10))

    period = open_period(books["org"].id)

    assert (period.start_date, period.end_date) == (
        date(2026, 2, 1),
        date(2026, 2, 28),
    )
    assert period.due_date == date(2026, 3, 25)


# --- settling --------------------------------------------------------------


def test_the_settlement_moves_the_vat_to_the_account_for_vat_payable(
    db_session, books, worked
):
    period = settle(books)

    entry = period.settlement_entry
    assert period.status == "settled"
    assert (period.start_date, period.end_date) == (
        date(2026, 1, 1),
        date(2026, 3, 31),
    )
    assert period.due_date == date(2026, 6, 1)
    assert period.period_type == "quarter"
    assert entry.entry_date == date(2026, 3, 31)
    assert entry.source_type == "vat_settlement"
    assert entry.source_id == period.id
    assert entry.description == "VAT settlement 2026-01-01 to 2026-03-31"
    assert sorted(shown(books, entry)) == [
        (7680, D("250.00"), D("0.00")),
        (7700, D("200.00"), D("0.00")),
        (7720, D("200.00"), D("0.00")),
        (7740, D("0.00"), D("406.25")),
        (7840, D("0.00"), D("243.75")),
    ]
    assert {item.vat_code_id for item in entry.lines} == {None}


def test_the_vat_accounts_are_zero_after_the_settlement(
    db_session, books, worked
):
    settle(books)

    after = balances(books)
    for number in (7680, 7700, 7720, 7740):
        assert after.get(number, D(0)) == D(0)
    assert after[7840] == D("-243.75")  # a credit: owed to the tax authority


def test_a_period_to_be_refunded_is_debited_to_the_receivable_account(
    db_session, books
):
    purchase(books, date(2026, 2, 10))

    period = settle(books)

    assert sorted(shown(books, period.settlement_entry)) == [
        (6320, D("200.00"), D("0.00")),
        (7740, D("0.00"), D("200.00")),
    ]
    assert balances(books)[6320] == D("200.00")


def test_a_period_where_the_vat_cancels_has_no_account_for_the_difference(
    db_session, books
):
    sale(books, date(2026, 1, 10), "800")
    purchase(books, date(2026, 1, 12), "800")

    period = settle(books)

    assert sorted(shown(books, period.settlement_entry)) == [
        (7680, D("200.00"), D("0.00")),
        (7740, D("0.00"), D("200.00")),
    ]


def test_a_period_with_only_codes_that_carry_no_vat_has_nothing_to_move(
    db_session, books
):
    post(
        books,
        date(2026, 2, 1),
        [
            line(books, 6480, debit="400"),
            line(books, 1150, "S23", credit="400"),
        ],
    )

    period = settle(books)

    assert period.status == "settled"
    assert period.settlement_entry_id is None
    assert (
        JournalEntry.query.filter_by(source_type="vat_settlement").count() == 0
    )


def test_a_credit_note_larger_than_the_sales_is_cleared_the_other_way(
    db_session, books
):
    post(
        books,
        date(2026, 1, 10),
        [
            line(books, 1010, "S01", debit="1000"),
            line(books, 6480, credit="1250"),
        ],
    )

    period = settle(books)

    assert sorted(shown(books, period.settlement_entry)) == [
        (6320, D("250.00"), D("0.00")),
        (7680, D("0.00"), D("250.00")),
    ]
    assert balances(books)[7680] == D(0)


def test_the_report_of_a_settled_period_still_shows_its_figures_and_ties(
    db_session, books, worked
):
    before = vat_report(books["org"].id, date(2026, 1, 1), date(2026, 3, 31))
    settle(books)

    after = vat_report(books["org"].id, date(2026, 1, 1), date(2026, 3, 31))

    assert after["total_to_pay"] == before["total_to_pay"] == D("243.75")
    assert after["ledger_check"]["ties"] is True
    assert after["ledger_check"]["uncoded_lines"] == []


def test_the_settlement_is_written_to_the_audit_log(db_session, books, worked):
    period = settle(books)

    row = AuditLog.query.filter_by(
        action="vat_period.settled", entity_id=period.id
    ).one()
    assert row.user_id == books["user"].id
    assert row.details["start_date"] == "2026-01-01"
    assert row.details["end_date"] == "2026-03-31"
    assert row.details["due_date"] == "2026-06-01"
    assert row.details["total_to_pay"] == "243.75"
    assert row.details["settlement_voucher_no"] == (
        period.settlement_entry.voucher_no
    )


def test_the_next_period_starts_the_day_after_and_is_settled_next(
    db_session, books, worked
):
    first = settle(books)

    following = open_period(books["org"].id)
    second = settle(books)

    assert following.start_date == first.end_date + timedelta(days=1)
    assert (second.start_date, second.end_date) == (
        date(2026, 4, 1),
        date(2026, 6, 30),
    )
    assert second.settlement_entry_id is None  # nothing happened in it


def test_a_change_of_type_works_from_the_next_period(db_session, books, worked):
    settle(books)
    books["org"].vat_period_type = "month"
    db_session.commit()

    period = open_period(books["org"].id)

    assert (period.start_date, period.end_date) == (
        date(2026, 4, 1),
        date(2026, 4, 30),
    )
    assert period.period_type == "month"


# --- what settling refuses --------------------------------------------------


def nothing_was_written(books):
    assert count(VatPeriod, books) == 0
    assert (
        JournalEntry.query.filter_by(source_type="vat_settlement").count() == 0
    )
    assert AuditLog.query.filter_by(action="vat_period.settled").count() == 0


def test_an_organization_that_is_not_registered_cannot_settle(
    db_session, books
):
    books["org"].vat_period_type = None
    db_session.commit()

    with pytest.raises(LedgerConflict) as error:
        settle(books)

    assert "not VAT-registered" in str(error.value)


def test_there_is_nothing_to_settle_before_a_code_is_posted(db_session, books):
    with pytest.raises(LedgerConflict) as error:
        settle(books)

    assert "nothing to settle" in str(error.value)
    nothing_was_written(books)


def test_a_period_cannot_be_settled_before_it_has_ended(
    db_session, books, worked
):
    with pytest.raises(LedgerConflict) as error:
        settle(books, today=date(2026, 3, 31))

    assert "has not ended" in str(error.value)
    assert "from 2026-04-01" in str(error.value)
    nothing_was_written(books)


def test_the_day_after_the_period_it_can_be_settled(db_session, books, worked):
    assert settle(books, today=date(2026, 4, 1)).status == "settled"


def test_postings_on_the_vat_accounts_without_a_code_stop_the_settlement(
    db_session, books, worked
):
    post(
        books,
        date(2026, 3, 15),
        [line(books, 6480, debit="30"), line(books, 7680, credit="30")],
        "VAT by hand",
    )
    counter = LedgerCounter.query.filter_by(
        organization_id=books["org"].id
    ).one()
    next_number = counter.next_voucher_no

    with pytest.raises(LedgerConflict) as error:
        settle(books)

    assert "1 posting(s)" in str(error.value)
    assert "no VAT code" in str(error.value)
    nothing_was_written(books)
    db_session.refresh(counter)
    assert counter.next_voucher_no == next_number


def test_uncoded_postings_that_cancel_leave_the_report_and_the_ledger_in_agreement(
    db_session, books, worked
):
    post(
        books,
        date(2026, 3, 15),
        [line(books, 7680, debit="30"), line(books, 7680, credit="30")],
    )

    assert settle(books).status == "settled"


def test_the_fix_for_an_uncoded_posting_is_to_reverse_it_in_the_period(
    db_session, books, worked
):
    bad = post(
        books,
        date(2026, 3, 15),
        [line(books, 6480, debit="30"), line(books, 7680, credit="30")],
    )
    with pytest.raises(LedgerConflict):
        settle(books)

    # Dated in the period, the reversal cancels the posting there
    reverse_entry(
        books["org"].id, books["user"].id, bad.id, entry_date=date(2026, 3, 16)
    )

    assert settle(books).status == "settled"


def test_a_reversal_dated_after_the_period_does_not_fix_it(
    db_session, books, worked
):
    bad = post(
        books,
        date(2026, 3, 15),
        [line(books, 6480, debit="30"), line(books, 7680, credit="30")],
    )
    reverse_entry(books["org"].id, books["user"].id, bad.id)

    with pytest.raises(LedgerConflict):
        settle(books)


def test_a_closed_fiscal_year_stops_the_settlement_and_leaves_nothing(
    db_session, books, worked
):
    year = FiscalYear.query.filter_by(organization_id=books["org"].id).one()
    year.status = "closed"
    db_session.commit()

    with pytest.raises(LedgerConflict) as error:
        settle(books)

    assert "is closed" in str(error.value)
    nothing_was_written(books)


def test_a_chart_without_the_account_for_vat_payable_stops_the_settlement(
    db_session, books, worked
):
    books["accounts"][7840].system_role = None
    db_session.commit()

    with pytest.raises(LedgerConflict) as error:
        settle(books)

    assert "vat_payable" in str(error.value)
    nothing_was_written(books)


def test_a_period_is_settled_once(db_session, books, worked):
    first = settle(books)

    # The same period cannot come up again
    assert open_period(books["org"].id).start_date > first.end_date
    assert (
        VatPeriod.query.filter_by(
            organization_id=books["org"].id, start_date=first.start_date
        ).count()
        == 1
    )


# --- the lock ---------------------------------------------------------------


def locked(books):
    """The books after a settled first quarter, and the voucher counter."""
    return LedgerCounter.query.filter_by(organization_id=books["org"].id).one()


def test_an_entry_with_a_vat_code_is_refused_in_a_settled_period(
    db_session, books, worked
):
    settle(books)
    counter = locked(books)
    next_number = counter.next_voucher_no
    entries = count(JournalEntry, books)

    with pytest.raises(LedgerConflict) as error:
        sale(books, date(2026, 3, 20))

    assert "VAT period 2026-01-01 to 2026-03-31 is settled" in str(error.value)
    assert count(JournalEntry, books) == entries
    db_session.refresh(counter)
    assert counter.next_voucher_no == next_number


def test_an_entry_on_a_vat_account_is_refused_in_a_settled_period(
    db_session, books, worked
):
    settle(books)

    for number in (7680, 7700, 7720, 7740, 7840, 6320):
        with pytest.raises(LedgerConflict):
            post(
                books,
                date(2026, 3, 20),
                [
                    line(books, 6480, debit="10"),
                    line(books, number, credit="10"),
                ],
            )


def test_the_first_and_the_last_day_of_the_period_are_locked(
    db_session, books, worked
):
    settle(books)

    for day in (date(2026, 1, 1), date(2026, 3, 31)):
        with pytest.raises(LedgerConflict):
            sale(books, day)


def test_an_entry_that_does_not_touch_vat_is_allowed_in_a_settled_period(
    db_session, books, worked
):
    settle(books)

    entry = post(
        books,
        date(2026, 3, 20),
        [line(books, 2720, debit="5"), line(books, 6480, credit="5")],
        "A bank fee, posted late",
    )

    assert entry.entry_date == date(2026, 3, 20)


def test_a_code_without_vat_still_touches_vat(db_session, books, worked):
    settle(books)

    with pytest.raises(LedgerConflict):
        post(
            books,
            date(2026, 3, 20),
            [
                line(books, 6480, debit="100"),
                line(books, 1150, "S23", credit="100"),
            ],
        )


def test_an_entry_after_the_period_is_not_locked(db_session, books, worked):
    settle(books)

    entry = sale(books, date(2026, 4, 1))

    assert entry.entry_date == date(2026, 4, 1)


def test_an_entry_before_the_first_period_is_not_locked(
    db_session, books, worked
):
    settle(books)

    # Nothing is settled before 1 January 2026
    entry = sale(books, date(2025, 12, 31))

    assert entry.entry_date == date(2025, 12, 31)


def test_the_settlement_itself_is_let_through_the_lock(
    db_session, books, worked
):
    # It is dated on the last day of the period it settles
    period = settle(books)

    assert period.settlement_entry.entry_date == period.end_date


def test_a_reversal_of_an_entry_in_a_settled_period_falls_in_the_open_one(
    db_session, books, worked
):
    original = sale(books, date(2026, 1, 10), "100")
    settle(books)

    reversal = reverse_entry(
        books["org"].id,
        books["user"].id,
        original.id,
        entry_date=date(2026, 4, 2),
    )

    assert reversal.entry_date == date(2026, 4, 2)
    report = vat_report(books["org"].id, date(2026, 4, 1), date(2026, 6, 30))
    # The correction is in the period it was made in
    assert report["sales_vat"] == D("-25.00")
    assert report["ledger_check"]["ties"] is True


def test_the_reversal_of_an_entry_in_a_settled_period_is_dated_today_by_default(
    db_session, books, worked
):
    original = sale(books, date(2026, 1, 10), "100")
    settle(books)

    reversal = reverse_entry(books["org"].id, books["user"].id, original.id)

    assert reversal.entry_date == max(original.entry_date, date.today())


def test_a_reversal_dated_inside_a_settled_period_is_refused(
    db_session, books, worked
):
    original = sale(books, date(2026, 1, 10), "100")
    settle(books)

    with pytest.raises(LedgerConflict):
        reverse_entry(
            books["org"].id,
            books["user"].id,
            original.id,
            entry_date=date(2026, 3, 1),
        )
    assert (
        JournalEntry.query.filter_by(reverses_entry_id=original.id).count() == 0
    )


def test_a_settlement_cannot_be_reversed(db_session, books, worked):
    period = settle(books)

    with pytest.raises(LedgerConflict) as error:
        reverse_entry(
            books["org"].id, books["user"].id, period.settlement_entry_id
        )

    assert "settles a VAT period" in str(error.value)


def test_a_settled_period_of_another_organization_does_not_lock_mine(
    db_session, books, worked, country
):
    other = Organization(
        name="Other ApS",
        slug="other-aps",
        country_id=country.id,
        email="other@example.com",
        logo="",
        vat_period_type="quarter",
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
    theirs = {
        item.number: item
        for item in Account.query.filter_by(organization_id=other.id)
    }
    mine = {"org": other, "user": user, "accounts": theirs}
    sale(mine, date(2026, 1, 10))
    settle_period(other.id, user.id, LATER)

    # Mine is not settled, so a posting in the same dates is fine
    entry = sale(books, date(2026, 2, 10))

    assert entry.entry_date == date(2026, 2, 10)


def test_the_open_period_can_still_be_posted_in_whatever_the_date(
    db_session, books, worked
):
    settle(books)

    for day in (date(2026, 4, 1), date(2026, 6, 30), date(2026, 10, 1)):
        assert sale(books, day).entry_date == day


# --- filing ----------------------------------------------------------------


def test_a_period_is_filed_with_a_date_and_a_reference(
    db_session, books, worked
):
    period = settle(books)

    filed = file_period(
        books["org"].id,
        books["user"].id,
        period.id,
        filed_on=date(2026, 5, 20),
        reference="  TastSelv 12345  ",
        today=LATER,
    )

    assert filed.status == "filed"
    assert filed.filed_on == date(2026, 5, 20)
    assert filed.filed_by == books["user"].id
    assert filed.reference == "TastSelv 12345"


def test_the_filing_date_is_today_unless_given(db_session, books, worked):
    period = settle(books)

    filed = file_period(
        books["org"].id, books["user"].id, period.id, today=date(2026, 5, 29)
    )

    assert filed.filed_on == date(2026, 5, 29)
    assert filed.reference is None


def test_filing_is_written_to_the_audit_log_with_whether_it_was_on_time(
    db_session, books, worked
):
    period = settle(books)
    file_period(
        books["org"].id,
        books["user"].id,
        period.id,
        filed_on=date(2026, 6, 2),
        today=LATER,
    )

    row = AuditLog.query.filter_by(
        action="vat_period.filed", entity_id=period.id
    ).one()
    assert row.details["filed_on"] == "2026-06-02"
    assert row.details["due_date"] == "2026-06-01"
    assert row.details["on_time"] is False


def test_filing_on_the_due_date_is_on_time(db_session, books, worked):
    period = settle(books)
    file_period(
        books["org"].id,
        books["user"].id,
        period.id,
        filed_on=date(2026, 6, 1),
        today=LATER,
    )

    row = AuditLog.query.filter_by(action="vat_period.filed").one()
    assert row.details["on_time"] is True


def test_a_period_is_filed_once(db_session, books, worked):
    period = settle(books)
    file_period(books["org"].id, books["user"].id, period.id, today=LATER)

    with pytest.raises(LedgerConflict) as error:
        file_period(books["org"].id, books["user"].id, period.id, today=LATER)

    assert "already filed" in str(error.value)


@pytest.mark.parametrize(
    ("filed_on", "message"),
    [
        (date(2026, 11, 2), "in the future"),
        (date(2026, 3, 31), "before the period ends"),
        (date(2026, 1, 15), "before the period ends"),
    ],
)
def test_a_filing_date_that_cannot_be_is_refused(
    db_session, books, worked, filed_on, message
):
    period = settle(books)

    with pytest.raises(LedgerError) as error:
        file_period(
            books["org"].id,
            books["user"].id,
            period.id,
            filed_on=filed_on,
            today=LATER,
        )

    assert message in str(error.value)
    db_session.refresh(period)
    assert period.status == "settled"


def test_a_long_reference_is_refused(db_session, books, worked):
    period = settle(books)

    with pytest.raises(LedgerError):
        file_period(
            books["org"].id,
            books["user"].id,
            period.id,
            reference="x" * 101,
            today=LATER,
        )


def test_an_unknown_period_is_not_found(db_session, books):
    with pytest.raises(LedgerError) as error:
        file_period(books["org"].id, books["user"].id, 999, today=LATER)

    assert error.value.status == 404


def test_filing_does_not_lock_more_than_the_settlement_did(
    db_session, books, worked
):
    period = settle(books)
    file_period(books["org"].id, books["user"].id, period.id, today=LATER)

    # Still allowed in a filed period: an entry that does not touch VAT
    post(
        books,
        date(2026, 3, 20),
        [line(books, 2720, debit="5"), line(books, 6480, credit="5")],
    )
    with pytest.raises(LedgerConflict):
        sale(books, date(2026, 3, 20))


def test_the_database_wants_a_filed_period_to_say_when_and_by_whom(
    db_session, books, worked
):
    from sqlalchemy.exc import IntegrityError

    period = settle(books)
    period.status = "filed"

    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


# --- the due date -----------------------------------------------------------


def test_the_due_date_can_be_corrected_and_the_change_is_logged(
    db_session, books, worked
):
    period = settle(books)

    changed = change_due_date(
        books["org"].id, books["user"].id, period.id, date(2026, 6, 2)
    )

    assert changed.due_date == date(2026, 6, 2)
    row = AuditLog.query.filter_by(action="vat_period.due_date_changed").one()
    assert row.details == {"from": "2026-06-01", "to": "2026-06-02"}


def test_a_due_date_before_the_period_ends_is_refused(
    db_session, books, worked
):
    period = settle(books)

    with pytest.raises(LedgerError):
        change_due_date(
            books["org"].id, books["user"].id, period.id, date(2026, 3, 31)
        )


# --- the API ---------------------------------------------------------------


def get(client, books):
    return client.get("/vat-periods", headers=books["headers"])


def test_the_api_lists_the_open_period_and_what_stops_it(client, books, worked):
    res = get(client, books)

    assert res.status_code == 200, res.get_json()
    body = res.get_json()
    assert body["vat_period_type"] == "quarter"
    assert body["periods"] == []
    assert body["open_period"] == {
        "period_type": "quarter",
        "start_date": "2026-01-01",
        "end_date": "2026-03-31",
        "due_date": "2026-06-01",
        "ended": True,
        "can_settle": True,
        "blocked_by": None,
    }


def test_the_api_says_when_the_period_has_not_ended(client, books):
    sale(books, date(2099, 2, 10))

    body = get(client, books).get_json()

    assert body["open_period"]["ended"] is False
    assert body["open_period"]["can_settle"] is False
    assert "has not ended" in body["open_period"]["blocked_by"]


def test_the_api_says_when_the_report_does_not_tie(client, books, worked):
    post(
        books,
        date(2026, 3, 15),
        [line(books, 6480, debit="30"), line(books, 7680, credit="30")],
    )

    body = get(client, books).get_json()

    assert body["open_period"]["can_settle"] is False
    assert "no VAT code" in body["open_period"]["blocked_by"]


def test_the_api_has_no_open_period_for_an_organization_without_vat(
    client, db_session, books
):
    books["org"].vat_period_type = None
    db_session.commit()

    body = get(client, books).get_json()

    assert body == {"vat_period_type": None, "periods": [], "open_period": None}


def test_the_api_settles_files_and_lists(client, books, worked):
    settled = client.post("/vat-periods/settle", headers=books["headers"])

    assert settled.status_code == 201, settled.get_json()
    period = settled.get_json()
    assert period["status"] == "settled"
    assert period["start_date"] == "2026-01-01"
    assert period["end_date"] == "2026-03-31"
    assert period["due_date"] == "2026-06-01"
    assert period["settlement_voucher_no"] is not None
    assert period["filed_on"] is None

    filed = client.post(
        f"/vat-periods/{period['id']}/file",
        json={"filed_on": "2026-05-30", "reference": "TastSelv 1"},
        headers=books["headers"],
    )

    assert filed.status_code == 200, filed.get_json()
    assert filed.get_json()["status"] == "filed"
    assert filed.get_json()["filed_on"] == "2026-05-30"
    assert filed.get_json()["reference"] == "TastSelv 1"
    listed = get(client, books).get_json()
    assert [item["id"] for item in listed["periods"]] == [period["id"]]
    assert listed["open_period"]["start_date"] == "2026-04-01"


def test_the_api_files_with_no_body(client, books, worked):
    period = client.post(
        "/vat-periods/settle", headers=books["headers"]
    ).get_json()

    res = client.post(
        f"/vat-periods/{period['id']}/file", headers=books["headers"]
    )

    assert res.status_code == 200, res.get_json()
    assert res.get_json()["filed_on"] == date.today().isoformat()


def test_the_api_corrects_the_due_date(client, books, worked):
    period = client.post(
        "/vat-periods/settle", headers=books["headers"]
    ).get_json()

    res = client.patch(
        f"/vat-periods/{period['id']}",
        json={"due_date": "2026-06-02"},
        headers=books["headers"],
    )

    assert res.status_code == 200, res.get_json()
    assert res.get_json()["due_date"] == "2026-06-02"


def test_the_api_refuses_to_settle_with_409_and_the_reason(client, books):
    sale(books, date(2099, 2, 10))

    res = client.post("/vat-periods/settle", headers=books["headers"])

    assert res.status_code == 409
    assert "has not ended" in res.get_json()["error"]


def test_the_api_refuses_a_locked_entry_with_409(client, books, worked):
    client.post("/vat-periods/settle", headers=books["headers"])

    res = client.post(
        "/journal-entries",
        json={
            "entry_date": "2026-03-20",
            "description": "Late sale",
            "lines": [
                {"account_id": books["accounts"][6480].id, "debit": 125},
                {
                    "account_id": books["accounts"][1010].id,
                    "credit": 100,
                    "vat_code": "S01",
                },
            ],
        },
        headers=books["headers"],
    )

    assert res.status_code == 409
    assert "is settled" in res.get_json()["error"]


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/vat-periods/1/file", {"filed_on": "yesterday"}),
        ("/vat-periods/1/file", {"unknown": 1}),
        ("/vat-periods/1/file", {"reference": "x" * 501}),
        ("/vat-periods/1/file", ["not", "an", "object"]),
    ],
)
def test_the_api_refuses_a_bad_filing_request(
    client, books, worked, path, body
):
    client.post("/vat-periods/settle", headers=books["headers"])

    res = client.post(path, json=body, headers=books["headers"])

    assert res.status_code == 422, res.get_json()


def test_the_api_refuses_a_bad_due_date_request(client, books, worked):
    period = client.post(
        "/vat-periods/settle", headers=books["headers"]
    ).get_json()

    for body in ({}, {"due_date": "soon"}, {"due_date": "2026-03-01"}):
        res = client.patch(
            f"/vat-periods/{period['id']}", json=body, headers=books["headers"]
        )
        assert res.status_code == 422, body


def test_the_api_cannot_find_a_period_of_another_organization(
    client, db_session, books, worked, country
):
    other = Organization(
        name="Other ApS",
        slug="other-aps",
        country_id=country.id,
        email="other@example.com",
        logo="",
        vat_period_type="quarter",
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
    period = client.post(
        "/vat-periods/settle", headers=books["headers"]
    ).get_json()
    strangers = headers(user)

    assert (
        client.post(
            f"/vat-periods/{period['id']}/file", headers=strangers
        ).status_code
        == 404
    )
    assert (
        client.patch(
            f"/vat-periods/{period['id']}",
            json={"due_date": "2026-07-01"},
            headers=strangers,
        ).status_code
        == 404
    )
    assert (
        client.get("/vat-periods", headers=strangers).get_json()["periods"]
        == []
    )


@pytest.mark.parametrize(
    ("method", "url"),
    [
        ("get", "/vat-periods"),
        ("post", "/vat-periods/settle"),
        ("post", "/vat-periods/1/file"),
        ("patch", "/vat-periods/1"),
    ],
)
def test_the_vat_periods_need_a_login(client, method, url):
    assert getattr(client, method)(url).status_code == 401


# --- random entries ---------------------------------------------------------


@pytest.mark.parametrize("seed", range(30))
def test_whatever_the_mix_of_codes_the_settlement_clears_the_vat_accounts(
    db_session, books, seed
):
    generator = random.Random(seed)
    for number in range(generator.randint(1, 12)):
        lines, _nets = random_entry(books, generator)
        day = date(2026, generator.randint(1, 3), generator.randint(1, 28))
        entry = post(books, day, lines, f"Entry {number}")
        if generator.random() < 0.2:
            reverse_entry(
                books["org"].id,
                books["user"].id,
                entry.id,
                entry_date=day + timedelta(days=1),
            )
    report = vat_report(books["org"].id, date(2026, 1, 1), date(2026, 3, 31))

    period = settle(books)

    after = balances(books, up_to=date(2026, 3, 31))
    for number in (7680, 7700, 7720, 7740):
        assert after.get(number, D(0)) == D(0)
    total = report["total_to_pay"]
    assert after.get(7840, D(0)) == -max(total, D(0))
    assert after.get(6320, D(0)) == max(-total, D(0))
    if period.settlement_entry is not None:
        entry = period.settlement_entry
        assert sum((i.debit for i in entry.lines), D(0)) == sum(
            (i.credit for i in entry.lines), D(0)
        )
    assert trial_balance(books["org"].id)["balanced"]
    # The report of the period is what it was
    after_report = vat_report(
        books["org"].id, date(2026, 1, 1), date(2026, 3, 31)
    )
    assert after_report["total_to_pay"] == total
    assert after_report["ledger_check"]["ties"] is True
