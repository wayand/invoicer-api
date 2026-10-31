"""
The money rules, in one place (see docs/money-rules.md).

All money is Decimal, never float. Amounts have 2 decimals and are rounded half
up (ties go away from zero, as PostgreSQL does when it coerces to a column's
scale). Quantities and unit prices have 3 decimals.

An invoice is added up like this:

    line amount = round(quantity x unit price)
    net total   = sum of the line amounts
    base        = the sum of the line amounts of one VAT code
    VAT         = round(base x rate), once per code
    gross total = net total + the VAT of every code

Each line is rounded before the lines are added, so the totals always match
the lines as printed. The VAT is rounded once per code, as the VAT engine
(app/vat_engine.py) does for a posting.
"""

from collections.abc import Iterable, Mapping
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
class CodeTotal:
    """The VAT of one code: what a Danish invoice shows by rate."""

    code: str
    rate: Decimal
    base: Decimal
    vat: Decimal


@dataclass(frozen=True)
class Totals:
    lines: tuple[Decimal, ...]
    amount: Decimal
    vat_amount: Decimal
    gross_amount: Decimal
    by_code: tuple[CodeTotal, ...]


def vat_by_code(
    lines: Iterable[tuple[Decimal, str]], rates: Mapping[str, Decimal]
) -> tuple[CodeTotal, ...]:
    """The base and the VAT of every code, in the order the codes first
    appear, from (line amount, code) pairs. `rates` gives the rate of each
    code (0 for a code that carries no VAT)."""
    bases: dict[str, Decimal] = {}
    for amount, code in lines:
        bases[code] = bases.get(code, Decimal("0.00")) + amount
    return tuple(
        CodeTotal(code, rates[code], base, round_money(base * rates[code]))
        for code, base in bases.items()
    )


def invoice_totals(
    lines: Iterable[tuple[Decimal, Decimal, str]],
    rates: Mapping[str, Decimal],
) -> Totals:
    """Add up (quantity, unit price, VAT code) triples. Raises MoneyError if
    an amount is too large to be stored."""
    coded = [(line_amount(qty, price), code) for qty, price, code in lines]
    amounts = tuple(amount for amount, _code in coded)
    net = sum(amounts, Decimal("0.00"))
    by_code = vat_by_code(coded, rates)
    vat = sum((item.vat for item in by_code), Decimal("0.00"))
    gross = net + vat
    if any(
        abs(value) > MAX_AMOUNT
        for value in (
            *amounts,
            net,
            vat,
            gross,
            *(item.base for item in by_code),
            *(item.vat for item in by_code),
        )
    ):
        raise MoneyError("An amount on the invoice is too large")
    return Totals(
        lines=amounts,
        amount=net,
        vat_amount=vat,
        gross_amount=gross,
        by_code=by_code,
    )


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
