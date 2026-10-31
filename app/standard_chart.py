"""Erhvervsstyrelsen's standard chart of accounts and VAT codes.

Reads the two official files in app/seed/standard (see SOURCE.md there).
docs/chart-of-accounts.md explains how the chart is used.
"""

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

STANDARD_DIR = Path(__file__).parent / "seed" / "standard"
CHART_FILE = STANDARD_DIR / "2026-01-01-Standardkontoplan.json"
VAT_CODES_FILE = STANDARD_DIR / "2026-01-01-Momskoder-Bruttoliste.json"

HEADING = "hovedkonto"
GROUP = "gruppekonto"
ACCOUNT = "konto"
SUM = "sumkonto"


@dataclass(frozen=True)
class StandardAccount:
    number: int
    name: str
    # HEADING and GROUP are headings, ACCOUNT is an account inside a group
    # (or a heading without sub-accounts), SUM is a total calculated from a
    # range of accounts (never posted to).
    kind: str
    group: int | None = None


@dataclass(frozen=True)
class VatCode:
    group: str
    code: str
    new_code: str
    name: str
    title: str
    rate: str
    deduction: str
    vat_return: str
    # The date the list is valid from, as in the file (yyyy-mm-dd)
    valid_from: str


def _read(path: Path) -> dict:
    with path.open(encoding="utf-8") as file:
        return json.load(file)


@lru_cache(maxsize=1)
def standard_accounts() -> dict[int, StandardAccount]:
    """Every account of the standard chart by number: headings, groups,
    accounts and sum accounts."""
    data = _read(CHART_FILE)
    accounts: dict[int, StandardAccount] = {}

    def add(item: dict, kind: str, group: int | None) -> None:
        number = item["kontonummer"]
        if number in accounts:
            raise ValueError(f"Account {number} is listed twice")
        accounts[number] = StandardAccount(
            number=number,
            name=item["navn"].strip(),
            kind=kind,
            group=group,
        )

    for item in data["Kontoplan"]:
        add(item, item["kontotype"], None)
        for child in item.get("konti") or []:
            add(child, ACCOUNT, item["kontonummer"])
    for item in data["Sumkonti"]["Konti"]:
        add(item, SUM, None)
    return accounts


@lru_cache(maxsize=1)
def standard_vat_codes() -> tuple[VatCode, ...]:
    """The official VAT codes (momskoder), in the order of the file."""
    data = _read(VAT_CODES_FILE)
    return tuple(
        VatCode(
            group=group["momsgruppe"],
            code=item["momskode"],
            new_code=item["momskode NY"],
            name=item["momskode betegnelse NY"],
            title=item["overskrift"].strip(),
            rate=item["momssats"],
            deduction=item["fradragsret"],
            vat_return=item["momsangivelse"],
            valid_from=data["File info"]["Valid from date"],
        )
        for group in data["momskoder - bruttoliste"]
        for item in group["momskoder"]
    )
