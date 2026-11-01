"""The ledger reports: the account ledger, the trial balance and the VAT
report.

All read the journal and nothing else, by the date of the entry
(`entry_date`), over a plain range of dates: they do not care which fiscal
year an entry is in. Reversals are entries like any other, so a reversed
entry nets out. See docs/ledger-design.md.

A balance is debit minus credit, as a signed amount: a debit balance is
positive and a credit balance negative. The account's normal balance (debit
or credit) is returned next to it, so a screen can show a credit-normal
account such as sales as a positive number.

The VAT report (docs/vat-design.md, section 6) is not a balance: it gives the
VAT of the range as the return asks for it, as positive amounts.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import and_, case, false, func, true

from app.ledger import LedgerError, LedgerNotFound
from app.models.account import Account, AccountType
from app.models.base import db
from app.models.ledger import JournalEntry, JournalLine
from app.models.vat_code import VatCode
from app.vat import SALES
from app.vat_engine import (
    ACQUISITION_GOODS_VAT,
    ACQUISITION_SERVICES_VAT,
    BASE,
    INPUT_VAT,
    NONDEDUCTIBLE,
    OUTPUT_VAT,
    VAT,
)

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


# The accounts that hold VAT, in the order of the return. Each is positive on
# one side: owed VAT on the credit side, input VAT on the debit side.
VAT_REPORT_ROLES = (
    OUTPUT_VAT,
    INPUT_VAT,
    ACQUISITION_GOODS_VAT,
    ACQUISITION_SERVICES_VAT,
)
BOXES = ("a_goods", "a_services", "b_goods", "b_services", "c")


def _in_range(query, date_from: date | None, date_to: date | None):
    if date_from:
        query = query.filter(JournalEntry.entry_date >= date_from)
    if date_to:
        query = query.filter(JournalEntry.entry_date <= date_to)
    return query


def _vat_side(role: str, debit: Decimal, credit: Decimal) -> Decimal:
    """What a VAT account holds, as a positive amount on its own side."""
    return debit - credit if role == INPUT_VAT else credit - debit


def vat_report(
    organization_id: int,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict:
    """The VAT of the range as the return asks for it: the VAT owed on sales,
    the input VAT, the VAT on purchases from abroad, the net amounts of the
    boxes A, B and C, and the total to pay (negative: to be refunded). Each
    figure is also given per VAT code.

    Then the check against the ledger: for each VAT account, its balance in
    the range next to the figure above. They are equal when every posting on
    the account has a VAT code. A posting without one (a voucher typed with
    its own VAT line) is the difference, and is listed."""
    _check_range(date_from, date_to)

    coded = _in_range(
        _lines(organization_id)
        .filter(JournalLine.vat_part.isnot(None))
        .join(VatCode, VatCode.id == JournalLine.vat_code_id)
        .join(Account, Account.id == JournalLine.account_id),
        date_from,
        date_to,
    )
    groups = (
        coded.group_by(VatCode.id, JournalLine.vat_part, Account.system_role)
        .with_entities(
            VatCode.id,
            JournalLine.vat_part,
            Account.system_role,
            func.sum(JournalLine.debit),
            func.sum(JournalLine.credit),
        )
        .all()
    )
    vat_codes = {
        code.id: code
        for code in VatCode.query.filter(
            VatCode.id.in_({group[0] for group in groups})
        )
    }

    per_code: dict[int, dict] = {}
    for code_id, part, role, debit, credit in groups:
        code = vat_codes[code_id]
        item = per_code.setdefault(
            code_id,
            {
                "code": code.code,
                "title": code.title,
                "applies_to": code.applies_to,
                "direction": code.direction,
                "base_box": code.base_box,
                "rate": code.rate,
                "deduction": code.deduction,
                "base": ZERO,
                "output_vat": ZERO,
                "input_vat": ZERO,
                "acquisition_vat": ZERO,
                "nondeductible_vat": ZERO,
            },
        )
        if part == BASE:
            # A sale is a credit, a purchase a debit
            item["base"] += (
                credit - debit if code.applies_to == SALES else debit - credit
            )
        elif part == NONDEDUCTIBLE:
            item["nondeductible_vat"] += debit - credit
        elif part == VAT and role == OUTPUT_VAT:
            item["output_vat"] += credit - debit
        elif part == VAT and role == INPUT_VAT:
            item["input_vat"] += debit - credit
        elif part == VAT and role in (
            ACQUISITION_GOODS_VAT,
            ACQUISITION_SERVICES_VAT,
        ):
            item["acquisition_vat"] += credit - debit
    codes = sorted(per_code.values(), key=lambda item: item["code"])

    # The same figures as the return has them: acquisition VAT on goods and
    # on services are separate lines, so they are told apart by the account
    acquisition = {ACQUISITION_GOODS_VAT: ZERO, ACQUISITION_SERVICES_VAT: ZERO}
    for _code_id, part, role, debit, credit in groups:
        if part == VAT and role in acquisition:
            acquisition[role] += credit - debit
    sales_vat = sum((item["output_vat"] for item in codes), ZERO)
    input_vat = sum((item["input_vat"] for item in codes), ZERO)
    boxes = {box: ZERO for box in BOXES}
    for item in codes:
        if item["base_box"]:
            boxes[item["base_box"]] += item["base"]
    reported = {
        OUTPUT_VAT: sales_vat,
        INPUT_VAT: input_vat,
        ACQUISITION_GOODS_VAT: acquisition[ACQUISITION_GOODS_VAT],
        ACQUISITION_SERVICES_VAT: acquisition[ACQUISITION_SERVICES_VAT],
    }

    # The check against the ledger: every line on a VAT account, coded or not
    accounts = {
        account.system_role: account
        for account in Account.query.filter(
            Account.organization_id == organization_id,
            Account.system_role.in_(VAT_REPORT_ROLES),
        )
    }
    balances = {
        account_id: (debit, credit)
        for account_id, debit, credit in _in_range(
            _lines(organization_id).filter(
                JournalLine.account_id.in_(
                    [account.id for account in accounts.values()]
                )
            ),
            date_from,
            date_to,
        )
        .group_by(JournalLine.account_id)
        .with_entities(
            JournalLine.account_id,
            func.sum(JournalLine.debit),
            func.sum(JournalLine.credit),
        )
    }
    check = []
    for role in VAT_REPORT_ROLES:
        account = accounts.get(role)
        debit, credit = (
            balances.get(account.id, (ZERO, ZERO))
            if account
            else (
                ZERO,
                ZERO,
            )
        )
        ledger = _vat_side(role, debit, credit)
        check.append(
            {
                "role": role,
                "account": None
                if account is None
                else {
                    "id": account.id,
                    "number": account.number,
                    "name": account.name,
                },
                "ledger_balance": ledger,
                "reported": reported[role],
                "difference": ledger - reported[role],
            }
        )

    uncoded = (
        _in_range(
            _lines(organization_id)
            .filter(
                JournalLine.vat_part.is_(None),
                JournalLine.account_id.in_(
                    [account.id for account in accounts.values()]
                ),
            )
            .join(Account, Account.id == JournalLine.account_id),
            date_from,
            date_to,
        )
        .with_entities(
            JournalEntry.id,
            JournalEntry.voucher_no,
            JournalEntry.entry_date,
            JournalEntry.description,
            Account.id,
            Account.number,
            Account.name,
            Account.system_role,
            JournalLine.description,
            JournalLine.debit,
            JournalLine.credit,
        )
        .order_by(
            JournalEntry.entry_date,
            JournalEntry.voucher_no,
            JournalLine.line_no,
        )
        .all()
    )
    uncoded_lines = [
        {
            "entry_id": entry_id,
            "voucher_no": voucher_no,
            "entry_date": day,
            "description": entry_text,
            "account": {"id": account_id, "number": number, "name": name},
            "role": role,
            "line_description": line_text,
            "debit": debit,
            "credit": credit,
        }
        for (
            entry_id,
            voucher_no,
            day,
            entry_text,
            account_id,
            number,
            name,
            role,
            line_text,
            debit,
            credit,
        ) in uncoded
    ]

    return {
        "date_from": date_from,
        "date_to": date_to,
        "sales_vat": sales_vat,
        "input_vat": input_vat,
        "eu_goods_vat": reported[ACQUISITION_GOODS_VAT],
        "eu_services_vat": reported[ACQUISITION_SERVICES_VAT],
        "total_to_pay": sales_vat
        + reported[ACQUISITION_GOODS_VAT]
        + reported[ACQUISITION_SERVICES_VAT]
        - input_vat,
        "boxes": boxes,
        "codes": codes,
        "ledger_check": {
            "accounts": check,
            "uncoded_lines": uncoded_lines,
            "ties": all(item["difference"] == ZERO for item in check),
        },
    }
