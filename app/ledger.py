"""The posting service: the one way an entry gets into the journal.

An entry is checked here before the database sees it (amounts, accounts,
balance, fiscal year), then written with the next voucher number. The
database triggers (see docs/ledger-design.md) are the last line of defence:
they refuse an unbalanced entry and any change to a posted one, whatever code
tried it. A mistake is corrected with `reverse_entry`, never by an edit.

A line can carry a VAT code. The service then adds the VAT lines itself, with
the engine in app/vat_engine.py (docs/vat-design.md): a caller sends the net
amounts and never a VAT amount of its own.

The functions flush but do not commit: the caller commits, or rolls back.
Nothing is half done if an error is raised, because the writes are in a
savepoint. Each change writes its audit log row (app/audit.py) in the same
transaction, so the log and the books always agree.
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from app.audit import record
from app.models.account import Account
from app.models.base import db
from app.models.contact import Contact
from app.models.ledger import (
    FiscalYear,
    JournalEntry,
    JournalLine,
    LedgerCounter,
)
from app.models.organization import Organization
from app.models.vat_code import VatCode
from app.models.vat_period import SETTLEMENT, VatPeriod
from app.money import MAX_AMOUNT, round_money
from app.vat_engine import (
    BASE,
    NONDEDUCTIBLE,
    VAT_ACCOUNT_ROLES,
    VAT_PARTS,
    NetLine,
    Rule,
    vat_lines,
)

# Dates outside these years are typing mistakes, and would open a fiscal year
# nobody wants
FIRST_YEAR, LAST_YEAR = 2000, 2100
MAX_LINES = 500
MAX_TEXT = 255


class LedgerError(ValueError):
    """The entry cannot be posted as asked. The message says why."""

    status = 422


class LedgerConflict(LedgerError):
    """The books are in a state that does not allow it: a closed fiscal
    year, an entry that is already reversed."""

    status = 409


class LedgerNotFound(LedgerError):
    status = 404


@dataclass(frozen=True)
class LineInput:
    account_id: int
    debit: Decimal = Decimal("0")
    credit: Decimal = Decimal("0")
    description: str | None = None
    contact_id: int | None = None
    # The code of a line that carries VAT (the new name, S01 or K010). A caller
    # sets this and nothing else.
    vat_code: str | None = None
    # What the line is, as far as VAT goes (base, vat or nondeductible). Set
    # by the service, and by a reversal, which copies the lines as they are.
    vat_part: str | None = None


def _text(value: str | None, what: str, required: bool = True) -> str | None:
    value = (value or "").strip()
    if not value:
        if required:
            raise LedgerError(f"{what} is required")
        return None
    if len(value) > MAX_TEXT:
        raise LedgerError(f"{what} is longer than {MAX_TEXT} characters")
    return value


def _check_each(lines: Sequence[LineInput]) -> list[LineInput]:
    """The lines with their amounts rounded as the money rules say, after
    checking that each is one side of an entry."""
    if len(lines) < 2:
        raise LedgerError("An entry needs at least 2 lines")
    if len(lines) > MAX_LINES:
        raise LedgerError(f"An entry has at most {MAX_LINES} lines")

    checked = []
    for number, line in enumerate(lines, start=1):
        debit, credit = round_money(line.debit), round_money(line.credit)
        if debit < 0 or credit < 0:
            raise LedgerError(f"Line {number}: an amount cannot be negative")
        if (debit > 0) == (credit > 0):
            raise LedgerError(
                f"Line {number}: needs either a debit or a credit above 0, "
                "not both and not neither"
            )
        if max(debit, credit) > MAX_AMOUNT:
            raise LedgerError(f"Line {number}: the amount is too large")
        checked.append(
            LineInput(
                account_id=line.account_id,
                debit=debit,
                credit=credit,
                description=_text(
                    line.description, f"Line {number} description", False
                ),
                contact_id=line.contact_id,
                vat_code=line.vat_code,
                vat_part=line.vat_part,
            )
        )
    return checked


def _check_balance(lines: Sequence[LineInput], with_vat: bool) -> None:
    if len(lines) > MAX_LINES:
        raise LedgerError(f"An entry has at most {MAX_LINES} lines")
    debit_total = sum((line.debit for line in lines), Decimal("0.00"))
    credit_total = sum((line.credit for line in lines), Decimal("0.00"))
    if debit_total != credit_total:
        raise LedgerError(
            f"The entry does not balance: debit {debit_total}, "
            f"credit {credit_total}"
            + (" (with the VAT lines)" if with_vat else "")
        )


def _role_accounts(organization_id: int, roles) -> dict[str, int]:
    """The account id of each role. The organization must have them all."""
    found = {
        account.system_role: account.id
        for account in Account.query.filter(
            Account.organization_id == organization_id,
            Account.system_role.in_(set(roles)),
        )
    }
    for role in sorted(set(roles) - found.keys()):
        raise LedgerConflict(
            f"The organization has no account with role {role}"
        )
    return found


def _with_vat(
    organization_id: int, lines: list[LineInput], add_vat: bool
) -> tuple[list[LineInput], bool]:
    """The lines with the VAT lines the engine adds for the ones that carry a
    code, and whether it added any.

    With add_vat False (a reversal) the lines are a copy of posted ones: they
    carry their parts already, and nothing is calculated again."""
    coded = {line.vat_code for line in lines if line.vat_code}
    for number, line in enumerate(lines, start=1):
        if add_vat:
            if line.vat_part is not None:
                raise LedgerError(
                    f"Line {number}: the VAT part is set by the server"
                )
        elif (line.vat_code is None) != (line.vat_part is None):
            raise LedgerError(f"Line {number}: VAT code and part go together")
        elif line.vat_part is not None and line.vat_part not in VAT_PARTS:
            raise LedgerError(f"Line {number}: unknown VAT part")
    if not coded:
        return lines, False
    codes = {
        code.code: code
        for code in VatCode.query.filter(VatCode.code.in_(coded))
    }
    for number, line in enumerate(lines, start=1):
        if line.vat_code and line.vat_code not in codes:
            raise LedgerError(
                f"Line {number}: there is no VAT code {line.vat_code}"
            )
    if not add_vat:
        return lines, False

    organization = db.session.get(Organization, organization_id)
    if organization.vat_period_type is None:
        raise LedgerError(
            "The organization is not VAT-registered: set its VAT period "
            "before using VAT codes"
        )
    on_vat_account = {
        account.id: account
        for account in Account.query.filter(
            Account.organization_id == organization_id,
            Account.id.in_({line.account_id for line in lines}),
            Account.system_role.in_(VAT_ACCOUNT_ROLES),
        )
    }
    net, base = [], []
    for number, line in enumerate(lines, start=1):
        if not line.vat_code:
            base.append(line)
            continue
        code = codes[line.vat_code]
        if not code.is_supported:
            raise LedgerError(
                f"Line {number}: the VAT code {code.code} cannot be used yet"
            )
        if line.account_id in on_vat_account:
            raise LedgerError(
                f"Line {number}: a VAT code cannot be used on the VAT "
                f"account {on_vat_account[line.account_id].number}"
            )
        net.append(
            NetLine(
                account_id=line.account_id,
                debit=line.debit,
                credit=line.credit,
                rule=Rule(
                    code=code.code,
                    applies_to=code.applies_to,
                    rate=code.rate,
                    deduction=code.deduction,
                    direction=code.direction,
                ),
            )
        )
        base.append(replace(line, vat_part=BASE))

    added = vat_lines(net)
    accounts = _role_accounts(
        organization_id, {item.role for item in added if item.role}
    )
    for item in added:
        label = "Non-deductible VAT" if item.part == NONDEDUCTIBLE else "VAT"
        base.append(
            LineInput(
                account_id=accounts[item.role]
                if item.role
                else item.account_id,
                debit=item.debit,
                credit=item.credit,
                description=f"{label} {item.code}",
                vat_code=item.code,
                vat_part=item.part,
            )
        )
    return base, bool(added)


def _check_accounts_and_contacts(
    organization_id: int, lines: Sequence[LineInput]
) -> None:
    ids = {line.account_id for line in lines}
    found = {
        account.id: account
        for account in Account.query.filter(
            Account.organization_id == organization_id, Account.id.in_(ids)
        )
    }
    for number, line in enumerate(lines, start=1):
        account = found.get(line.account_id)
        if account is None:
            raise LedgerError(
                f"Line {number}: there is no account with id {line.account_id}"
            )
        if account.is_archived:
            raise LedgerError(
                f"Line {number}: account {account.number} {account.name} "
                "is archived"
            )

    contact_ids = {line.contact_id for line in lines if line.contact_id}
    if contact_ids:
        known = {
            contact.id
            for contact in Contact.query.filter(
                Contact.organization_id == organization_id,
                Contact.id.in_(contact_ids),
            )
        }
        for number, line in enumerate(lines, start=1):
            if line.contact_id and line.contact_id not in known:
                raise LedgerError(
                    f"Line {number}: there is no contact with id "
                    f"{line.contact_id}"
                )


def fiscal_year_for(
    organization_id: int, day: date, user_id: int
) -> FiscalYear:
    """The open fiscal year that covers the day. If no fiscal year covers it,
    the calendar year is opened (and logged as opened by user_id), unless that
    would overlap another year."""
    year = FiscalYear.query.filter(
        FiscalYear.organization_id == organization_id,
        FiscalYear.start_date <= day,
        FiscalYear.end_date >= day,
    ).first()
    if year is not None:
        if year.status != "open":
            raise LedgerConflict(
                f"The fiscal year {year.start_date} to {year.end_date} "
                "is closed"
            )
        return year

    start, end = date(day.year, 1, 1), date(day.year, 12, 31)
    overlapping = FiscalYear.query.filter(
        FiscalYear.organization_id == organization_id,
        FiscalYear.start_date <= end,
        FiscalYear.end_date >= start,
    ).first()
    if overlapping is not None:
        raise LedgerConflict(
            f"No fiscal year covers {day}, and opening the calendar year "
            f"{day.year} would overlap the fiscal year "
            f"{overlapping.start_date} to {overlapping.end_date}"
        )
    try:
        with db.session.begin_nested():
            year = FiscalYear(
                organization_id=organization_id, start_date=start, end_date=end
            )
            db.session.add(year)
            db.session.flush()
            record(
                organization_id,
                user_id,
                "fiscal_year.opened",
                "fiscal_year",
                year.id,
                {
                    "start_date": start,
                    "end_date": end,
                    "opened_by": "the first posting in the year",
                },
            )
    except IntegrityError:
        # Someone else opened it a moment ago
        year = FiscalYear.query.filter_by(
            organization_id=organization_id, start_date=start
        ).one()
        if year.status != "open":
            raise LedgerConflict(f"The fiscal year {day.year} is closed")
    return year


def lock_ledger(organization_id: int) -> LedgerCounter:
    """Lock the books of the organization until the transaction ends. Every
    posting takes the same lock, so what is checked after it is taken cannot
    change under the caller: a settlement and a posting happen one at a
    time."""
    db.session.execute(
        insert(LedgerCounter)
        .values(organization_id=organization_id)
        .on_conflict_do_nothing()
    )
    return (
        LedgerCounter.query.filter_by(organization_id=organization_id)
        .with_for_update()
        .one()
    )


def _take_voucher_no(organization_id: int) -> int:
    """The next voucher number. The row is locked until the transaction ends,
    so numbers are taken one at a time, and a posting that fails gives its
    number back: the sequence has no gaps."""
    counter = lock_ledger(organization_id)
    number = counter.next_voucher_no
    counter.next_voucher_no = number + 1
    return number


def _check_vat_lock(
    organization_id: int, entry_date: date, lines: Sequence[LineInput]
) -> None:
    """An entry that touches VAT cannot be posted in a settled VAT period: a
    line with a VAT code, or a line on one of the VAT accounts. Other entries
    can (docs/vat-design.md, section 8). The books are locked when this runs,
    so a settlement cannot slip in between the check and the posting."""
    period = VatPeriod.query.filter(
        VatPeriod.organization_id == organization_id,
        VatPeriod.start_date <= entry_date,
        VatPeriod.end_date >= entry_date,
    ).first()
    if period is None:
        return
    touches_vat = any(line.vat_code for line in lines) or (
        db.session.query(Account.id)
        .filter(
            Account.organization_id == organization_id,
            Account.id.in_({line.account_id for line in lines}),
            Account.system_role.in_(VAT_ACCOUNT_ROLES),
        )
        .first()
        is not None
    )
    if touches_vat:
        raise LedgerConflict(
            f"The VAT period {period.start_date} to {period.end_date} is "
            "settled: an entry that touches VAT cannot be dated in it. "
            "Date it in the open period"
        )


def post_entry(
    organization_id: int,
    user_id: int,
    entry_date: date,
    description: str,
    lines: Sequence[LineInput],
    *,
    source_type: str = "manual",
    source_id: int | None = None,
    reverses_entry_id: int | None = None,
    add_vat: bool = True,
    ignore_vat_lock: bool = False,
) -> JournalEntry:
    """Post a balanced entry with the next voucher number. Raises LedgerError
    if it cannot be posted, and then nothing is written.

    A line with a `vat_code` is a net line: the VAT lines for it are added
    here, so the lines given must balance with them. A reversal passes
    add_vat=False and the lines of the entry it reverses, VAT lines included.

    An entry that touches VAT is refused (409) in a settled VAT period. Only
    the settlement itself, which belongs to the period, is let through with
    `ignore_vat_lock`.
    """
    description = _text(description, "The description")
    if not FIRST_YEAR <= entry_date.year <= LAST_YEAR:
        raise LedgerError(
            f"The date must be in {FIRST_YEAR} to {LAST_YEAR}: {entry_date}"
        )
    checked = _check_each(lines)
    checked, with_vat = _with_vat(organization_id, checked, add_vat)
    _check_balance(checked, with_vat)
    _check_accounts_and_contacts(organization_id, checked)
    used_codes = {line.vat_code for line in checked if line.vat_code}
    vat_code_ids = (
        {
            code.code: code.id
            for code in VatCode.query.filter(VatCode.code.in_(used_codes))
        }
        if used_codes
        else {}
    )

    with db.session.begin_nested():
        year = fiscal_year_for(organization_id, entry_date, user_id)
        voucher_no = _take_voucher_no(organization_id)
        if not ignore_vat_lock:
            _check_vat_lock(organization_id, entry_date, checked)
        entry = JournalEntry(
            organization_id=organization_id,
            fiscal_year_id=year.id,
            voucher_no=voucher_no,
            entry_date=entry_date,
            description=description,
            source_type=source_type,
            source_id=source_id,
            reverses_entry_id=reverses_entry_id,
            created_by=user_id,
        )
        db.session.add(entry)
        db.session.flush()
        for number, line in enumerate(checked, start=1):
            db.session.add(
                JournalLine(
                    journal_entry_id=entry.id,
                    organization_id=organization_id,
                    line_no=number,
                    account_id=line.account_id,
                    debit=line.debit,
                    credit=line.credit,
                    description=line.description,
                    contact_id=line.contact_id,
                    vat_code_id=vat_code_ids.get(line.vat_code),
                    vat_part=line.vat_part,
                )
            )
        db.session.flush()
        details = {
            "voucher_no": entry.voucher_no,
            "entry_date": entry_date,
            "fiscal_year_id": year.id,
            "source_type": source_type,
            "line_count": len(checked),
            "debit_total": sum(
                (line.debit for line in checked), Decimal("0.00")
            ),
        }
        if vat_code_ids:
            details["vat_codes"] = sorted(vat_code_ids)
        record(
            organization_id,
            user_id,
            "journal_entry.posted",
            "journal_entry",
            entry.id,
            details,
        )
        # The database checks the balance when the transaction ends. Ask now,
        # so that a problem is raised here and rolled back with this entry.
        db.session.execute(
            db.text(
                "SET CONSTRAINTS journal_entries_balanced, "
                "journal_lines_balanced IMMEDIATE"
            )
        )
        db.session.execute(
            db.text(
                "SET CONSTRAINTS journal_entries_balanced, "
                "journal_lines_balanced DEFERRED"
            )
        )
    return entry


def get_entry(organization_id: int, entry_id: int) -> JournalEntry:
    entry = JournalEntry.query.filter_by(
        organization_id=organization_id, id=entry_id
    ).first()
    if entry is None:
        raise LedgerNotFound(f"There is no entry with id {entry_id}")
    return entry


def reverse_entry(
    organization_id: int,
    user_id: int,
    entry_id: int,
    *,
    entry_date: date | None = None,
    description: str | None = None,
) -> JournalEntry:
    """Post the opposite of an entry: the same accounts with debit and credit
    swapped. An entry is reversed once, and a reversal is not reversed (post
    a new entry instead). The reversal is dated today unless told otherwise,
    or on the date of the entry if that is later, so that it never comes
    before the entry it cancels."""
    original = get_entry(organization_id, entry_id)
    if original.source_type == SETTLEMENT:
        raise LedgerConflict(
            f"Voucher {original.voucher_no} settles a VAT period: it cannot "
            "be reversed, a mistake in a settled period is corrected in a "
            "later one"
        )
    if original.reverses_entry_id is not None:
        raise LedgerConflict(
            f"Voucher {original.voucher_no} is a reversal: it cannot be "
            "reversed, post a new entry instead"
        )
    reversed_by = JournalEntry.query.filter_by(
        reverses_entry_id=original.id
    ).first()
    if reversed_by is not None:
        raise LedgerConflict(
            f"Voucher {original.voucher_no} is already reversed by voucher "
            f"{reversed_by.voucher_no}"
        )

    lines = [
        LineInput(
            account_id=line.account_id,
            debit=line.credit,
            credit=line.debit,
            description=line.description,
            contact_id=line.contact_id,
            vat_code=line.vat_code.code if line.vat_code_id else None,
            vat_part=line.vat_part,
        )
        for line in original.lines
    ]
    if not description:
        description = f"Reversal of voucher {original.voucher_no}: "
        description += original.description
        description = description[:MAX_TEXT]
    try:
        reversal = post_entry(
            organization_id,
            user_id,
            entry_date or max(original.entry_date, date.today()),
            description,
            lines,
            source_type="reversal",
            source_id=original.id,
            reverses_entry_id=original.id,
            add_vat=False,
        )
        record(
            organization_id,
            user_id,
            "journal_entry.reversed",
            "journal_entry",
            original.id,
            {
                "voucher_no": original.voucher_no,
                "reversal_entry_id": reversal.id,
                "reversal_voucher_no": reversal.voucher_no,
            },
        )
        return reversal
    except IntegrityError as error:
        # Two reversals at the same moment: the second one loses
        if "reverses_entry_id" in str(error):
            raise LedgerConflict(
                f"Voucher {original.voucher_no} is already reversed"
            ) from error
        raise


def close_fiscal_year(
    organization_id: int, fiscal_year_id: int, user_id: int
) -> FiscalYear:
    """Close a fiscal year: nothing more can be posted in it."""
    year = FiscalYear.query.filter_by(
        organization_id=organization_id, id=fiscal_year_id
    ).first()
    if year is None:
        raise LedgerNotFound(
            f"There is no fiscal year with id {fiscal_year_id}"
        )
    if year.status == "closed":
        raise LedgerConflict("The fiscal year is already closed")
    year.status = "closed"
    db.session.flush()
    record(
        organization_id,
        user_id,
        "fiscal_year.closed",
        "fiscal_year",
        year.id,
        {"start_date": year.start_date, "end_date": year.end_date},
    )
    return year
