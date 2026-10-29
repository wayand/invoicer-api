"""The ledger reports: the account ledger and the trial balance.

Both read the journal and nothing else, by the date of the entry
(`entry_date`), over a plain range of dates: they do not care which fiscal
year an entry is in. Reversals are entries like any other, so a reversed
entry nets out. See docs/ledger-design.md.

A balance is debit minus credit, as a signed amount: a debit balance is
positive and a credit balance negative. The account's normal balance (debit
or credit) is returned next to it, so a screen can show a credit-normal
account such as sales as a positive number.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import and_, case, false, func, true

from app.ledger import LedgerError, LedgerNotFound
from app.models.account import Account, AccountType
from app.models.base import db
from app.models.ledger import JournalEntry, JournalLine

ZERO = Decimal("0.00")


@dataclass
class LedgerRow:
    entry_id: int
    voucher_no: int
    entry_date: date
    description: str
    line_description: str | None
    debit: Decimal
    credit: Decimal
    balance: Decimal


def _check_range(date_from: date | None, date_to: date | None) -> None:
    if date_from and date_to and date_from > date_to:
        raise LedgerError("The from date is after the to date")


def _lines(organization_id: int):
    """The lines of the organization with the date of their entry."""
    return (
        db.session.query(JournalLine)
        .join(
            JournalEntry,
            (JournalEntry.id == JournalLine.journal_entry_id)
            & (JournalEntry.organization_id == JournalLine.organization_id),
        )
        .filter(JournalLine.organization_id == organization_id)
    )


def account_ledger(
    organization_id: int,
    account_id: int,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict:
    """Every posting on one account in the range, with a running balance,
    and the balance carried in from before the range."""
    _check_range(date_from, date_to)
    account = (
        db.session.query(Account, AccountType.normal_balance)
        .join(AccountType, AccountType.id == Account.account_type_id)
        .filter(
            Account.organization_id == organization_id,
            Account.id == account_id,
        )
        .first()
    )
    if account is None:
        raise LedgerNotFound(f"There is no account with id {account_id}")
    account, normal_balance = account

    opening = ZERO
    if date_from:
        opening = (
            _lines(organization_id)
            .filter(
                JournalLine.account_id == account_id,
                JournalEntry.entry_date < date_from,
            )
            .with_entities(
                func.coalesce(
                    func.sum(JournalLine.debit - JournalLine.credit), ZERO
                )
            )
            .scalar()
        )

    query = _lines(organization_id).filter(JournalLine.account_id == account_id)
    if date_from:
        query = query.filter(JournalEntry.entry_date >= date_from)
    if date_to:
        query = query.filter(JournalEntry.entry_date <= date_to)
    postings = query.with_entities(
        JournalEntry.id,
        JournalEntry.voucher_no,
        JournalEntry.entry_date,
        JournalEntry.description,
        JournalLine.description,
        JournalLine.debit,
        JournalLine.credit,
    ).order_by(
        JournalEntry.entry_date, JournalEntry.voucher_no, JournalLine.line_no
    )

    balance = opening
    rows = []
    for (
        entry_id,
        voucher_no,
        day,
        entry_text,
        line_text,
        debit,
        credit,
    ) in postings:
        balance += debit - credit
        rows.append(
            LedgerRow(
                entry_id=entry_id,
                voucher_no=voucher_no,
                entry_date=day,
                description=entry_text,
                line_description=line_text,
                debit=debit,
                credit=credit,
                balance=balance,
            )
        )
    return {
        "account": {
            "id": account.id,
            "number": account.number,
            "name": account.name,
            "normal_balance": normal_balance,
        },
        "date_from": date_from,
        "date_to": date_to,
        "opening_balance": opening,
        "total_debit": sum((row.debit for row in rows), ZERO),
        "total_credit": sum((row.credit for row in rows), ZERO),
        "closing_balance": balance,
        "rows": rows,
    }


def trial_balance(
    organization_id: int,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict:
    """For every account with a posting up to the end of the range: the
    balance before the range, what was debited and credited in it, and the
    balance at the end. Each total is zero or equal on both sides, because
    every entry balances; `balanced` says whether they are."""
    _check_range(date_from, date_to)

    # What is before the range counts only toward the opening balance, and
    # what is inside it toward the movements
    before = JournalEntry.entry_date < date_from if date_from else false()
    inside = and_(
        true(),
        *([JournalEntry.entry_date >= date_from] if date_from else []),
        *([JournalEntry.entry_date <= date_to] if date_to else []),
    )
    query = _lines(organization_id)
    if date_to:
        query = query.filter(JournalEntry.entry_date <= date_to)
    rows = (
        query.join(Account, Account.id == JournalLine.account_id)
        .join(AccountType, AccountType.id == Account.account_type_id)
        .group_by(
            Account.id,
            Account.number,
            Account.name,
            AccountType.name,
            AccountType.normal_balance,
            AccountType.report_type,
        )
        .with_entities(
            Account.id,
            Account.number,
            Account.name,
            AccountType.name,
            AccountType.normal_balance,
            AccountType.report_type,
            func.coalesce(
                func.sum(
                    case(
                        (before, JournalLine.debit - JournalLine.credit),
                        else_=ZERO,
                    )
                ),
                ZERO,
            ),
            func.coalesce(
                func.sum(case((inside, JournalLine.debit), else_=ZERO)), ZERO
            ),
            func.coalesce(
                func.sum(case((inside, JournalLine.credit), else_=ZERO)), ZERO
            ),
        )
        .order_by(Account.number)
        .all()
    )

    accounts = []
    for (
        id_,
        number,
        name,
        type_,
        normal,
        report,
        opening,
        debit,
        credit,
    ) in rows:
        accounts.append(
            {
                "account_id": id_,
                "number": number,
                "name": name,
                "account_type": type_,
                "normal_balance": normal,
                "report_type": report,
                "opening_balance": opening,
                "debit": debit,
                "credit": credit,
                "closing_balance": opening + debit - credit,
            }
        )
    opening_total = sum((item["opening_balance"] for item in accounts), ZERO)
    debit_total = sum((item["debit"] for item in accounts), ZERO)
    credit_total = sum((item["credit"] for item in accounts), ZERO)
    closing_total = sum((item["closing_balance"] for item in accounts), ZERO)
    return {
        "date_from": date_from,
        "date_to": date_to,
        "accounts": accounts,
        "total_opening_balance": opening_total,
        "total_debit": debit_total,
        "total_credit": credit_total,
        "total_closing_balance": closing_total,
        "balanced": opening_total == ZERO
        and closing_total == ZERO
        and debit_total == credit_total,
    }
