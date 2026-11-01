"""Approving an invoice: the invoice gets its number, is posted to the ledger,
and is locked (docs/invoice-posting-design.md, sections 4 to 7).

One transaction does all of it. The books of the organization are locked first,
the same lock every posting and the VAT settlement take, so the number, the
voucher and the checks cannot be overtaken by another posting. If anything is
refused, nothing is written: no number is used, no voucher number, no audit row.

The voucher is the receivable for the gross amount (with the customer), the
sales accounts for the lines, and, for an organization that is VAT-registered,
the VAT lines the engine adds. An organization that is not VAT-registered may
not show VAT on its invoices, so its invoice is posted without VAT codes.

The functions flush but do not commit, like the posting service.
"""

from datetime import date, datetime
from decimal import Decimal

from app.audit import record
from app.invoice_vat import (
    MAX_INVOICE_LINES,
    InvoiceVatError,
    apply_totals,
    sales_codes,
)
from app.ledger import (
    LedgerConflict,
    LedgerError,
    LedgerNotFound,
    LineInput,
    _role_accounts,
    lock_ledger,
    post_entry,
)
from app.models.account import Account
from app.models.base import db
from app.models.invoice import Invoice
from app.models.invoice_setting import InvoiceSetting
from app.models.organization import Organization
from app.models.product import Product

ZERO = Decimal("0.00")
CURRENCY = "DKK"
RECEIVABLES = "receivables"

# The account a sales line goes to when its product has none: the account with
# the role that belongs to the VAT code (docs/invoice-posting-design.md, 5)
SALES_ROLE = {
    "S01": "sales",
    "S02": "sales",
    "S81": "sales",
    "S82": "sales",
    "S24": "sales",
    "S43": "sales",
    "S21": "sales_eu_goods",
    "S22": "sales_eu_goods",
    "S23": "sales_eu_services",
    "S41": "sales_non_eu_goods",
    "S42": "sales_non_eu_services",
}


def _sales_accounts(organization_id: int, invoice: Invoice, setting) -> dict:
    """The account of each line of the invoice, by line id: the account of the
    product if it has one, else the account with the role of the VAT code,
    else, for the codes that go on `sales`, the default account of the
    settings."""
    product_ids = {line.product_id for line in invoice.lines}
    product_accounts = {
        product.id: product.account_id
        for product in Product.query.filter(
            Product.organization_id == organization_id,
            Product.id.in_(product_ids),
        )
        if product.account_id
    }
    own = {
        account.id
        for account in Account.query.filter(
            Account.organization_id == organization_id,
            Account.id.in_(set(product_accounts.values())),
        )
    }
    roles = {SALES_ROLE[line.vat_code.code] for line in invoice.lines}
    by_role = {
        account.system_role: account.id
        for account in Account.query.filter(
            Account.organization_id == organization_id,
            Account.system_role.in_(roles),
        )
    }
    accounts = {}
    for line in invoice.lines:
        role = SALES_ROLE[line.vat_code.code]
        account_id = product_accounts.get(line.product_id)
        if account_id not in own:
            account_id = by_role.get(role)
        if account_id is None and role == "sales":
            account_id = setting.default_account_id
        if account_id is None:
            raise LedgerConflict(
                f"The organization has no account with role {role}"
            )
        accounts[line.id] = account_id
    return accounts


def _number(
    organization_id: int, invoice: Invoice, setting, given: str | None
) -> str:
    """The number of the invoice. Sequential mode: the next number of the
    settings, which is used up now. Manual mode: the number the user gave."""
    if setting.invoice_no_mode == "sequential":
        number = str(max(setting.next_invoice_no, 1))
        setting.next_invoice_no = int(number) + 1
    else:
        number = (given or invoice.invoice_no or "").strip()
        if not number:
            raise LedgerError("The invoice needs a number")
        if len(number) > 100:
            raise LedgerError(
                "The invoice number is longer than 100 characters"
            )
        if number.isascii() and number.isdecimal():
            setting.next_invoice_no = int(number) + 1
    taken = Invoice.query.filter(
        Invoice.organization_id == organization_id,
        Invoice.invoice_no == number,
        Invoice.id != invoice.id,
    ).first()
    if taken is not None:
        raise LedgerConflict(
            f"The invoice number {number} is already used"
            + (
                ": set the next number in the invoice settings"
                if setting.invoice_no_mode == "sequential"
                else ""
            )
        )
    return number


def approve_invoice(
    organization_id: int,
    user_id: int,
    invoice_id: int,
    *,
    invoice_no: str | None = None,
    today: date | None = None,
) -> Invoice:
    """Approve a draft invoice: give it its number, post it, and lock it.
    Raises LedgerError (422), LedgerConflict (409) or LedgerNotFound (404),
    and then nothing is written."""
    today = today or date.today()
    with db.session.begin_nested():
        # Nothing else is posted, and no settlement happens, while this runs
        lock_ledger(organization_id)
        invoice = (
            Invoice.query.filter_by(
                organization_id=organization_id, id=invoice_id
            )
            .with_for_update()
            .first()
        )
        if invoice is None:
            raise LedgerNotFound(f"Invoice with id {invoice_id} not found!")
        if invoice.state != "draft":
            raise LedgerConflict(
                f"The invoice is already approved, as invoice "
                f"{invoice.invoice_no}"
            )
        setting = (
            InvoiceSetting.query.filter_by(organization_id=organization_id)
            .with_for_update()
            .first()
        )
        if setting is None:
            raise LedgerConflict(
                "Invoice settings are missing for this organization. Set "
                "them up under Settings, Invoicing before approving invoices."
            )
        organization = db.session.get(Organization, organization_id)
        registered = organization.vat_period_type is not None

        if invoice.currency_id != CURRENCY:
            raise LedgerError(
                f"Only invoices in {CURRENCY} can be approved, not "
                f"{invoice.currency_id}"
            )
        if invoice.invoice_date > today:
            raise LedgerError(
                f"The invoice date {invoice.invoice_date} is in the future"
            )
        if not invoice.lines:
            raise LedgerError("The invoice has no lines")
        if len(invoice.lines) > MAX_INVOICE_LINES:
            raise LedgerError(
                f"An invoice has at most {MAX_INVOICE_LINES} lines"
            )
        try:
            codes = sales_codes(
                {line.vat_code.code for line in invoice.lines}, registered
            )
        except InvoiceVatError as error:
            raise LedgerError(str(error)) from error
        # The totals are the server's: worked out again from the lines
        apply_totals(invoice, invoice.lines, {c.id: c for c in codes.values()})
        if all(line.amount == ZERO for line in invoice.lines):
            raise LedgerError("There is nothing to book: every line is 0")

        number = _number(organization_id, invoice, setting, invoice_no)
        accounts = _sales_accounts(organization_id, invoice, setting)
        receivables = _role_accounts(organization_id, {RECEIVABLES})[
            RECEIVABLES
        ]

        lines = []
        gross = invoice.gross_amount
        if gross != ZERO:
            lines.append(
                LineInput(
                    receivables,
                    debit=max(gross, ZERO),
                    credit=max(-gross, ZERO),
                    description=f"Invoice {number}",
                    contact_id=invoice.contact_id,
                )
            )
        for line in invoice.lines:
            if line.amount == ZERO:
                continue  # a line of text
            lines.append(
                LineInput(
                    accounts[line.id],
                    debit=max(-line.amount, ZERO),
                    credit=max(line.amount, ZERO),
                    description=line.description,
                    vat_code=line.vat_code.code if registered else None,
                )
            )
        entry = post_entry(
            organization_id,
            user_id,
            invoice.invoice_date,
            f"Invoice {number}",
            lines,
            source_type="invoice",
            source_id=invoice.id,
        )

        invoice.invoice_no = number
        invoice.state = "approved"
        invoice.journal_entry_id = entry.id
        invoice.approved_at = datetime.now()
        invoice.approved_by = user_id
        db.session.flush()
        record(
            organization_id,
            user_id,
            "invoice.approved",
            "invoice",
            invoice.id,
            {
                "invoice_no": number,
                "voucher_no": entry.voucher_no,
                "entry_id": entry.id,
                "invoice_date": invoice.invoice_date,
                "amount": invoice.amount,
                "vat_amount": invoice.vat_amount,
                "gross_amount": invoice.gross_amount,
                "contact_id": invoice.contact_id,
            },
        )
    return invoice
