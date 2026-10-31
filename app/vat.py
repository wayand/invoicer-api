"""The VAT codes (momskoder): our classification of the official list.

Erhvervsstyrelsen's list (app/seed/standard, see SOURCE.md there) describes
each code in words. This module says, for each code, what a program needs: the
rate and the deductible share as numbers, where the VAT is posted (`direction`)
and which box of the return the net amount goes to (`base_box`). A code that
phase 2 cannot calculate yet is `deferred`, with the reason.

docs/vat-design.md explains every choice. The `vat_codes` table is filled from
`vat_code_rows()` by a migration that holds the rows as data, and a test
compares the two, so a new official list fails the test until each of its
codes is classified here.
"""

from dataclasses import dataclass
from decimal import Decimal

from app.standard_chart import standard_vat_codes

SALES, PURCHASES = "sales", "purchases"

# Where the VAT of a code is posted
OUTPUT = "output"
INPUT = "input"
ACQUISITION_GOODS = "acquisition_goods"
ACQUISITION_SERVICES = "acquisition_services"
NO_VAT = "none"
DIRECTIONS = (OUTPUT, INPUT, ACQUISITION_GOODS, ACQUISITION_SERVICES, NO_VAT)

# The boxes of the return that a net amount is reported in (rubrik A, B, C)
BASE_BOXES = ("a_goods", "a_services", "b_goods", "b_services", "c")

# Why a code cannot be chosen yet (section 2 of docs/vat-design.md)
VARIABLE_DEDUCTION = "variable_deduction"
SPECIAL_SCHEME = "special_scheme"
OSS = "oss"
FIXED_SHARE_UNCONFIRMED = "fixed_share_unconfirmed"
DOMESTIC_REVERSE_CHARGE = "domestic_reverse_charge"
REFUND_SCHEME = "refund_scheme"
IMPORT_VAT = "import_vat"
TRIANGULAR_TRADE = "triangular_trade"
DEFERRED_REASONS = (
    VARIABLE_DEDUCTION,
    SPECIAL_SCHEME,
    OSS,
    FIXED_SHARE_UNCONFIRMED,
    DOMESTIC_REVERSE_CHARGE,
    REFUND_SCHEME,
    IMPORT_VAT,
    TRIANGULAR_TRADE,
)


@dataclass(frozen=True)
class Classification:
    direction: str
    base_box: str | None = None


C = Classification

# The codes phase 2 calculates, by the new code
SUPPORTED = {
    # Sales
    "S01": C(OUTPUT),
    "S02": C(NO_VAT, "c"),
    "S81": C(NO_VAT),
    "S82": C(NO_VAT),
    "S21": C(NO_VAT, "b_goods"),
    "S22": C(NO_VAT, "b_goods"),
    "S23": C(NO_VAT, "b_services"),
    "S24": C(NO_VAT),
    "S41": C(NO_VAT, "c"),
    "S42": C(NO_VAT, "c"),
    "S43": C(NO_VAT),
    # Purchases
    "K010": C(INPUT),
    "K030": C(NO_VAT),
    "K040": C(INPUT),
    "K070": C(INPUT),
    "K210": C(ACQUISITION_GOODS, "a_goods"),
    "K230": C(ACQUISITION_GOODS, "a_goods"),
    "K260": C(ACQUISITION_SERVICES, "a_services"),
    "K280": C(ACQUISITION_SERVICES, "a_services"),
    "K340": C(NO_VAT),
    "K460": C(ACQUISITION_SERVICES),
    "K480": C(ACQUISITION_SERVICES),
}

DEFERRED = {
    **dict.fromkeys(
        (
            "K020",
            "K090",
            "K100",
            "K110",
            "K120",
            "K130",
            "K220",
            "K240",
            "K250",
            "K270",
            "K290",
            "K300",
            "K310",
            "K320",
            "K420",
            "K440",
            "K450",
            "K470",
            "K490",
            "K500",
            "K670",
            "K680",
            "K700",
        ),
        VARIABLE_DEDUCTION,
    ),
    **dict.fromkeys(
        (
            "S83",
            "S84",
            "S85",
            "S86",
            "S87",
            "S88",
            "K620",
            "K630",
            "K640",
            "K650",
        ),
        SPECIAL_SCHEME,
    ),
    **dict.fromkeys(("S61", "S62", "S63", "S64", "S65"), OSS),
    **dict.fromkeys(
        ("K050", "K060", "K080", "K330", "K610"), FIXED_SHARE_UNCONFIRMED
    ),
    **dict.fromkeys(("K660", "K690"), DOMESTIC_REVERSE_CHARGE),
    **dict.fromkeys(("K710", "K720"), REFUND_SCHEME),
    **dict.fromkeys(("K410", "K430"), IMPORT_VAT),
    "S25": TRIANGULAR_TRADE,
}


def percent(text: str) -> Decimal | None:
    """A share written in the list ("25%", "66,6%") as a fraction (0.25,
    0.666), or None when the list gives no number: it is empty, or says "x%",
    "Skøn", "Delvis" and so on."""
    text = text.strip()
    if not text.endswith("%"):
        return None
    try:
        return Decimal(text[:-1].replace(",", ".")) / 100
    except ArithmeticError:
        return None


def applies_to(group: str) -> str:
    """The OSS group is sales too: it is online sales to consumers."""
    return SALES if group.startswith(("Salg", "OSS")) else PURCHASES


def vat_code_rows() -> list[dict]:
    """One row of the `vat_codes` table for each official code, in the order
    of the file. Raises ValueError if a code is not classified, or is
    classified twice."""
    codes = standard_vat_codes()
    known = {code.new_code for code in codes}
    both = SUPPORTED.keys() & DEFERRED.keys()
    if both:
        raise ValueError(f"Supported and deferred: {sorted(both)}")
    unknown = (SUPPORTED.keys() | DEFERRED.keys()) - known
    if unknown:
        raise ValueError(f"Not in the official list: {sorted(unknown)}")

    rows = []
    for code in codes:
        classification = SUPPORTED.get(code.new_code)
        reason = DEFERRED.get(code.new_code)
        if classification is None and reason is None:
            raise ValueError(f"{code.new_code} is not classified")
        rows.append(
            {
                "code": code.new_code,
                "legacy_code": code.code,
                "name": code.name,
                "title": code.title,
                "applies_to": applies_to(code.group),
                "rate": percent(code.rate),
                "deduction": percent(code.deduction),
                "direction": classification.direction
                if classification
                else None,
                "base_box": classification.base_box if classification else None,
                "is_supported": classification is not None,
                "deferred_reason": reason,
                "valid_from": code.valid_from,
            }
        )
    return rows
