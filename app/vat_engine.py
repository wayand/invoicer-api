"""The VAT engine: from the net lines of an entry to its VAT lines.

Pure calculation, no database: the posting service (app/ledger.py) gives it
the lines that carry a VAT code and posts what comes back. The rules are in
docs/vat-design.md, section 4, and the cases in tests/unit/vat_cases.json are
shared with the app.

For the lines of one entry that carry the same code:

    base = the sum of their net amounts, each already rounded
    VAT  = round(base x rate)           one rounding per code and entry
    deductible = round(VAT x deduction) for a purchase
    non-deductible = VAT - deductible

The net amount of a sales line is its credit minus its debit, and of a
purchase line its debit minus its credit, so a credit note has a negative base
and its VAT lands on the opposite side.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction

from app.money import CENT, round_money
from app.vat import (
    ACQUISITION_GOODS,
    ACQUISITION_SERVICES,
    NO_VAT,
    OUTPUT,
    SALES,
)

# What a journal line is, as far as VAT goes
BASE, VAT, NONDEDUCTIBLE = "base", "vat", "nondeductible"
VAT_PARTS = (BASE, VAT, NONDEDUCTIBLE)

# The accounts that hold VAT, by role. A VAT code does not go on these.
OUTPUT_VAT, INPUT_VAT = "output_vat", "input_vat"
ACQUISITION_GOODS_VAT, ACQUISITION_SERVICES_VAT = (
    "vat_eu_goods",
    "vat_eu_services",
)
VAT_ACCOUNT_ROLES = (
    OUTPUT_VAT,
    INPUT_VAT,
    ACQUISITION_GOODS_VAT,
    ACQUISITION_SERVICES_VAT,
    "vat_payable",
    "vat_receivable",
)

# The account the VAT itself is posted to, by direction
VAT_ROLE = {
    OUTPUT: OUTPUT_VAT,
    ACQUISITION_GOODS: ACQUISITION_GOODS_VAT,
    ACQUISITION_SERVICES: ACQUISITION_SERVICES_VAT,
}

ZERO = Decimal("0.00")


@dataclass(frozen=True)
class Rule:
    """What the engine needs to know about a code."""

    code: str
    applies_to: str
    rate: Decimal | None
    deduction: Decimal | None
    direction: str


@dataclass(frozen=True)
class NetLine:
    """A line that carries a VAT code: a sale or a cost, without VAT."""

    account_id: int
    debit: Decimal
    credit: Decimal
    rule: Rule

    @property
    def net(self) -> Decimal:
        if self.rule.applies_to == SALES:
            return self.credit - self.debit
        return self.debit - self.credit


@dataclass(frozen=True)
class VatLine:
    """A line the engine adds. It goes to the account with the role, or, for
    the non-deductible part, to an account of the entry (`account_id`)."""

    part: str
    code: str
    debit: Decimal
    credit: Decimal
    role: str | None = None
    account_id: int | None = None


def _side(amount: Decimal, positive: str) -> tuple[Decimal, Decimal]:
    """(debit, credit) for a signed amount, whose positive side is `positive`
    ("debit" or "credit")."""
    size = abs(amount)
    if (amount > 0) == (positive == "debit"):
        return size, ZERO
    return ZERO, size


def _cents(amount: Decimal) -> int:
    return int(amount * 100)


def allocate(total: Decimal, weights: Sequence[Decimal]) -> list[Decimal]:
    """Share an amount over the weights in proportion, to the cent, so that
    the shares add up to the amount exactly. What is left after rounding down
    goes to the largest remainders, the first of them when they are equal.
    The shares of a negative amount are those of its positive twin, negated,
    so a credit note divides like the invoice it corrects."""
    base = sum(_cents(weight) for weight in weights)
    if base == 0:
        return [ZERO for _ in weights]
    size = abs(_cents(total))
    shares = [Fraction(size * _cents(w), base) for w in weights]
    floors = [math.floor(share) for share in shares]
    left = size - sum(floors)
    by_remainder = sorted(
        range(len(shares)), key=lambda i: (floors[i] - shares[i], i)
    )
    for index in by_remainder[:left]:
        floors[index] += 1
    sign = -1 if total < 0 else 1
    return [(Decimal(sign * cents) / 100).quantize(CENT) for cents in floors]


def _group(lines: Sequence[NetLine]) -> dict[str, list[NetLine]]:
    """The lines by code, in the order the codes first appear."""
    groups: dict[str, list[NetLine]] = {}
    for line in lines:
        groups.setdefault(line.rule.code, []).append(line)
    return groups


def vat_lines(lines: Sequence[NetLine]) -> list[VatLine]:
    """The VAT lines of an entry, for the lines that carry a code, grouped by
    code in the order the codes first appear."""
    posted: list[VatLine] = []
    for code, group in _group(lines).items():
        rule = group[0].rule
        if rule.direction == NO_VAT or rule.rate is None:
            continue
        base = sum((line.net for line in group), ZERO)
        vat = round_money(base * rule.rate)
        if vat == 0:
            continue

        if rule.direction == OUTPUT:
            debit, credit = _side(vat, "credit")
            posted.append(VatLine(VAT, code, debit, credit, OUTPUT_VAT))
            continue

        # A purchase: part of the VAT can be deducted
        deductible = round_money(vat * (rule.deduction or Decimal("0")))
        if rule.direction in (ACQUISITION_GOODS, ACQUISITION_SERVICES):
            debit, credit = _side(vat, "credit")
            posted.append(
                VatLine(VAT, code, debit, credit, VAT_ROLE[rule.direction])
            )
        if deductible:
            debit, credit = _side(deductible, "debit")
            posted.append(VatLine(VAT, code, debit, credit, INPUT_VAT))
        nondeductible = vat - deductible
        if nondeductible:
            shares = allocate(nondeductible, [line.net for line in group])
            for line, share in zip(group, shares):
                if share:
                    debit, credit = _side(share, "debit")
                    posted.append(
                        VatLine(
                            NONDEDUCTIBLE,
                            code,
                            debit,
                            credit,
                            account_id=line.account_id,
                        )
                    )
    return posted
