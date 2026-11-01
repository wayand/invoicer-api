"""VAT periods: when a return is due, and how a period is settled and filed
(docs/vat-design.md, section 8).

An organization that is VAT-registered has a period type (month, quarter or
half-year). The periods follow each other without gaps. The first one starts
at the beginning of the calendar period of the first VAT-coded posting. Each
after it starts the day after the one before, and runs to the next boundary of
the type the organization has then, so a change of type works from the next
period on.

To settle the first open period, once it has ended, one voucher moves the
balances of the VAT accounts of the period to the VAT payable account (or to
the VAT receivable account, for a refund). A settled period locks the entries
that touch VAT (the posting service refuses them), and cannot be unsettled.

The functions flush but do not commit, like the posting service, and write
the audit log in the same transaction.
"""

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func

from app.audit import record
from app.ledger import (
    LedgerConflict,
    LedgerError,
    LedgerNotFound,
    LineInput,
    _role_accounts,
    _text,
    lock_ledger,
    post_entry,
)
from app.models.base import db
from app.models.ledger import JournalEntry, JournalLine
from app.models.organization import Organization
from app.models.vat_period import SETTLEMENT, VatPeriod
from app.reports import vat_report
from app.vat_engine import (
    ACQUISITION_GOODS_VAT,
    ACQUISITION_SERVICES_VAT,
    INPUT_VAT,
    OUTPUT_VAT,
)

ZERO = Decimal("0.00")
MAX_REFERENCE = 100
# What the vat_payable and vat_receivable accounts are called by role
VAT_PAYABLE, VAT_RECEIVABLE = "vat_payable", "vat_receivable"


def _add_months(year: int, month: int, months: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + months
    return index // 12, index % 12 + 1


def period_bounds(period_type: str, day: date) -> tuple[date, date]:
    """The first and last day of the month, quarter or half-year of the day."""
    size = {"month": 1, "quarter": 3, "half_year": 6}[period_type]
    first_month = (day.month - 1) // size * size + 1
    last_month = first_month + size - 1
    return (
        date(day.year, first_month, 1),
        date(
            day.year, last_month, calendar.monthrange(day.year, last_month)[1]
        ),
    )


def next_weekday(day: date) -> date:
    """The day, or the Monday after it if it is a Saturday or a Sunday."""
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


def due_date(period_type: str, end_date: date) -> date:
    """When the return and the payment are due, as the rules say, moved past a
    weekend. Quarters and half-years: the first day of the third month after
    the period ends (1 June for the first quarter). Months: the 25th of the
    next month. Holidays and the exceptions the tax authority makes are not
    known here, so the date can be corrected on the period."""
    if period_type == "month":
        year, month = _add_months(end_date.year, end_date.month, 1)
        return next_weekday(date(year, month, 25))
    year, month = _add_months(end_date.year, end_date.month, 3)
    return next_weekday(date(year, month, 1))


@dataclass(frozen=True)
class OpenPeriod:
    period_type: str
    start_date: date
    end_date: date
    due_date: date


def open_period(organization_id: int) -> OpenPeriod | None:
    """The first period that has not been settled, or None: the organization
    is not VAT-registered, or nothing has a VAT code yet."""
    organization = db.session.get(Organization, organization_id)
    period_type = organization.vat_period_type
    if period_type is None:
        return None
    last = (
        VatPeriod.query.filter_by(organization_id=organization_id)
        .order_by(VatPeriod.end_date.desc())
        .first()
    )
    if last is not None:
        start = last.end_date + timedelta(days=1)
    else:
        first = (
            db.session.query(func.min(JournalEntry.entry_date))
            .join(
                JournalLine,
                (JournalLine.journal_entry_id == JournalEntry.id)
                & (JournalLine.organization_id == JournalEntry.organization_id),
            )
            .filter(
                JournalEntry.organization_id == organization_id,
                JournalLine.vat_code_id.isnot(None),
            )
            .scalar()
        )
        if first is None:
            return None
        start = period_bounds(period_type, first)[0]
    end = period_bounds(period_type, start)[1]
    return OpenPeriod(period_type, start, end, due_date(period_type, end))


def _period(organization_id: int, period_id: int) -> VatPeriod:
    period = VatPeriod.query.filter_by(
        organization_id=organization_id, id=period_id
    ).first()
    if period is None:
        raise LedgerNotFound(f"There is no VAT period with id {period_id}")
    return period


def _settlement_lines(organization_id: int, report: dict) -> list[LineInput]:
    """The lines that move the VAT accounts of the period to the account for
    VAT payable (or receivable). Each account is cleared on the side it
    holds its balance, and the difference goes to one account."""
    balances = {
        item["role"]: item["ledger_balance"]
        for item in report["ledger_check"]["accounts"]
    }
    total = report["total_to_pay"]
    wanted = {role for role, amount in balances.items() if amount != ZERO}
    if total > ZERO:
        wanted.add(VAT_PAYABLE)
    elif total < ZERO:
        wanted.add(VAT_RECEIVABLE)
    accounts = _role_accounts(organization_id, wanted)

    lines = []
    # What is owed is credit-natured: clearing a credit balance is a debit
    for role in (OUTPUT_VAT, ACQUISITION_GOODS_VAT, ACQUISITION_SERVICES_VAT):
        amount = balances[role]
        if amount > ZERO:
            lines.append(LineInput(accounts[role], debit=amount))
        elif amount < ZERO:
            lines.append(LineInput(accounts[role], credit=-amount))
    # Input VAT is debit-natured: clearing a debit balance is a credit
    amount = balances[INPUT_VAT]
    if amount > ZERO:
        lines.append(LineInput(accounts[INPUT_VAT], credit=amount))
    elif amount < ZERO:
        lines.append(LineInput(accounts[INPUT_VAT], debit=-amount))
    if total > ZERO:
        lines.append(LineInput(accounts[VAT_PAYABLE], credit=total))
    elif total < ZERO:
        lines.append(LineInput(accounts[VAT_RECEIVABLE], debit=-total))
    return lines


def why_not_settled(
    organization_id: int, period: OpenPeriod, today: date
) -> str | None:
    """What stops the period from being settled, or None. The period is not
    over, or the report does not tie to the ledger: postings on the VAT
    accounts have no VAT code, and the return would not agree with the books.
    Uncoded postings that cancel (a posting and its reversal in the period)
    leave the report and the ledger in agreement, so they are no obstacle."""
    if today <= period.end_date:
        return (
            f"The VAT period {period.start_date} to {period.end_date} has "
            f"not ended: it can be settled from "
            f"{period.end_date + timedelta(days=1)}"
        )
    report = vat_report(organization_id, period.start_date, period.end_date)
    check = report["ledger_check"]
    if not check["ties"]:
        count = len(check["uncoded_lines"])
        return (
            f"The VAT report of {period.start_date} to {period.end_date} "
            f"does not agree with the VAT accounts: {count} posting(s) on "
            "them have no VAT code. Reverse them, dated in the period, and "
            "post them again with a VAT code"
        )
    return None


def settle_period(
    organization_id: int, user_id: int, today: date | None = None
) -> VatPeriod:
    """Settle the first open period: post the voucher that moves its VAT to
    the account for VAT payable or receivable, and record the period. Raises
    LedgerConflict (409) if there is nothing to settle, the period has not
    ended, or the report does not tie to the ledger. Nothing is written then.
    """
    today = today or date.today()
    organization = db.session.get(Organization, organization_id)
    if organization.vat_period_type is None:
        raise LedgerConflict(
            "The organization is not VAT-registered: set its VAT period "
            "before settling"
        )
    with db.session.begin_nested():
        # No posting can come in between the check and the settlement
        lock_ledger(organization_id)
        period = open_period(organization_id)
        if period is None:
            raise LedgerConflict(
                "There is nothing to settle: no posting has a VAT code yet"
            )
        problem = why_not_settled(organization_id, period, today)
        if problem:
            raise LedgerConflict(problem)

        report = vat_report(organization_id, period.start_date, period.end_date)
        lines = _settlement_lines(organization_id, report)
        row = VatPeriod(
            organization_id=organization_id,
            period_type=period.period_type,
            start_date=period.start_date,
            end_date=period.end_date,
            due_date=period.due_date,
            settled_by=user_id,
        )
        db.session.add(row)
        db.session.flush()
        entry = None
        if lines:
            entry = post_entry(
                organization_id,
                user_id,
                period.end_date,
                f"VAT settlement {period.start_date} to {period.end_date}",
                lines,
                source_type=SETTLEMENT,
                source_id=row.id,
                ignore_vat_lock=True,
            )
            row.settlement_entry_id = entry.id
        record(
            organization_id,
            user_id,
            "vat_period.settled",
            "vat_period",
            row.id,
            {
                "start_date": period.start_date,
                "end_date": period.end_date,
                "due_date": period.due_date,
                "period_type": period.period_type,
                "settlement_voucher_no": entry.voucher_no if entry else None,
                "sales_vat": report["sales_vat"],
                "input_vat": report["input_vat"],
                "eu_goods_vat": report["eu_goods_vat"],
                "eu_services_vat": report["eu_services_vat"],
                "total_to_pay": report["total_to_pay"],
            },
        )
    return row


def file_period(
    organization_id: int,
    user_id: int,
    period_id: int,
    *,
    filed_on: date | None = None,
    reference: str | None = None,
    today: date | None = None,
) -> VatPeriod:
    """Mark a settled period as filed: the return was entered in TastSelv
    Erhverv on `filed_on` (today if not given), with an optional reference.
    Filing locks nothing more than the settlement did; it records that the
    deadline was met."""
    today = today or date.today()
    period = _period(organization_id, period_id)
    if period.status == "filed":
        raise LedgerConflict(
            f"The VAT period {period.start_date} to {period.end_date} is "
            f"already filed, on {period.filed_on}"
        )
    filed_on = filed_on or today
    if filed_on > today:
        raise LedgerError("The filing date cannot be in the future")
    if filed_on <= period.end_date:
        raise LedgerError("The return cannot be filed before the period ends")
    reference = _text(reference, "The reference", required=False)
    if reference and len(reference) > MAX_REFERENCE:
        raise LedgerError(
            f"The reference is longer than {MAX_REFERENCE} characters"
        )
    period.status = "filed"
    period.filed_on = filed_on
    period.filed_by = user_id
    period.reference = reference
    db.session.flush()
    record(
        organization_id,
        user_id,
        "vat_period.filed",
        "vat_period",
        period.id,
        {
            "start_date": period.start_date,
            "end_date": period.end_date,
            "due_date": period.due_date,
            "filed_on": filed_on,
            "on_time": filed_on <= period.due_date,
            "reference": reference,
        },
    )
    return period


def change_due_date(
    organization_id: int, user_id: int, period_id: int, new_date: date
) -> VatPeriod:
    """Correct the due date of a period: holidays and the exceptions the tax
    authority makes are not known to the program."""
    period = _period(organization_id, period_id)
    if new_date <= period.end_date:
        raise LedgerError("The due date must be after the period ends")
    old = period.due_date
    period.due_date = new_date
    db.session.flush()
    record(
        organization_id,
        user_id,
        "vat_period.due_date_changed",
        "vat_period",
        period.id,
        {"from": old, "to": new_date},
    )
    return period


def list_periods(organization_id: int) -> list[VatPeriod]:
    return (
        VatPeriod.query.filter_by(organization_id=organization_id)
        .order_by(VatPeriod.start_date.desc())
        .all()
    )
