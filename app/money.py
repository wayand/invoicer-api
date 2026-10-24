"""
The money rules, in one place (see docs/money-rules.md).

All money is Decimal, never float. Amounts have 2 decimals and are rounded half
up (ties go away from zero, as PostgreSQL does when it coerces to a column's
scale). Quantities and unit prices have 3 decimals.

An invoice is added up like this:

    line amount = round(quantity x unit price)
    net total   = sum of the line amounts
    VAT         = round(net total x rate)
    gross total = net total + VAT

Each line is rounded before the lines are added, so the totals always match
the lines as printed.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from marshmallow import fields

CENT = Decimal("0.01")

# The largest amount a NUMERIC(14,2) column holds
MAX_AMOUNT = Decimal("999999999999.99")
# The largest quantity or unit price a NUMERIC(14,3) column holds
MAX_FACTOR = Decimal("99999999999.999")


class MoneyError(ValueError):
    """An amount that cannot be stored."""


def round_money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def line_amount(quantity: Decimal, unit_price: Decimal) -> Decimal:
    return round_money(quantity * unit_price)


@dataclass(frozen=True)
class Totals:
    lines: tuple[Decimal, ...]
    amount: Decimal
    vat_amount: Decimal
    gross_amount: Decimal


def invoice_totals(
    lines: Iterable[tuple[Decimal, Decimal]], vat_rate: Decimal
) -> Totals:
    """Add up (quantity, unit price) pairs. Raises MoneyError if an amount is
    too large to be stored."""
    amounts = tuple(line_amount(qty, price) for qty, price in lines)
    net = sum(amounts, Decimal("0.00"))
    vat = round_money(net * vat_rate)
    gross = net + vat
    if any(abs(value) > MAX_AMOUNT for value in (*amounts, net, vat, gross)):
        raise MoneyError("An amount on the invoice is too large")
    return Totals(lines=amounts, amount=net, vat_amount=vat, gross_amount=gross)


class DecimalNumber(fields.Decimal):
    """A Decimal read with the money rounding and written as a JSON number.

    Negative values are numbers like any other: credit lines and credit notes
    need them.
    """

    def __init__(self, *, places: int, **kwargs):
        super().__init__(places=places, rounding=ROUND_HALF_UP, **kwargs)

    def _serialize(self, value, attr, obj, **kwargs):
        serialized = super()._serialize(value, attr, obj, **kwargs)
        return None if serialized is None else float(serialized)
