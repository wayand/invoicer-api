"""The VAT of an invoice: one VAT code per line (docs/vat-design.md, section 7).

An invoice is not posted yet, so there is no VAT line to add: the routes use
this module to check the codes of the lines, and to set the amounts of the
lines and the totals of the invoice. The numbers are those of the VAT engine
(app/vat_engine.py), which posts an invoice in phase 3: the lines of one code
add up to a base, and the VAT is rounded once per code.
"""

from collections.abc import Iterable, Sequence
from decimal import Decimal

from app.models.vat_code import VatCode
from app.money import CodeTotal, invoice_totals, vat_by_code
from app.vat import OUTPUT, SALES

NO_RATE = Decimal("0")


class InvoiceVatError(ValueError):
    """A VAT code that an invoice line cannot have."""


def sales_rate(code: VatCode) -> Decimal:
    """The rate an invoice charges for a code: the rate of a code with VAT
    on the sale, and 0 for the codes that carry none (the sale is exempt,
    abroad or outside the VAT law)."""
    if code.direction == OUTPUT and code.rate is not None:
        return code.rate
    return NO_RATE


def sales_codes(codes: Iterable[str]) -> dict[str, VatCode]:
    """The VAT codes with these names, for the lines of an invoice. Raises
    InvoiceVatError for a code that does not exist, one for purchases, or one
    that cannot be used yet."""
    wanted = set(codes)
    found = {
        code.code: code
        for code in VatCode.query.filter(VatCode.code.in_(wanted))
    }
    for name in sorted(wanted):
        code = found.get(name)
        if code is None:
            raise InvoiceVatError(f"There is no VAT code {name}")
        if code.applies_to != SALES:
            raise InvoiceVatError(
                f"The VAT code {name} is for purchases and cannot be used "
                "on an invoice"
            )
        if not code.is_supported:
            raise InvoiceVatError(f"The VAT code {name} cannot be used yet")
    return found


def apply_totals(invoice, lines: Sequence, codes: dict[int, VatCode]) -> None:
    """Set the amount of every line and the totals of the invoice from the
    quantities, unit prices and VAT codes (docs/money-rules.md). Whatever
    amounts the client sent are not used. `codes` has the VAT code of every
    line by its id."""
    rates = {code.code: sales_rate(code) for code in codes.values()}
    totals = invoice_totals(
        [
            (line.quantity, line.unit_price, codes[line.vat_code_id].code)
            for line in lines
        ],
        rates,
    )
    for line, amount in zip(lines, totals.lines):
        line.amount = amount
    invoice.amount = totals.amount
    invoice.vat_amount = totals.vat_amount
    invoice.gross_amount = totals.gross_amount


def vat_summary(invoice) -> tuple[CodeTotal, ...]:
    """The VAT of a saved invoice by code (code, rate, base, vat), as a
    Danish invoice must show it. Worked out from the saved line amounts."""
    lines = [(line.amount, line.vat_code.code) for line in invoice.lines]
    rates = {
        line.vat_code.code: sales_rate(line.vat_code) for line in invoice.lines
    }
    return vat_by_code(lines, rates)
