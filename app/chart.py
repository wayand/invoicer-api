"""The starter chart of accounts of an organization.

A small set of accounts from Erhvervsstyrelsen's standard chart, with the
roles the posting service looks accounts up by, and our own Skattekonto. See
docs/chart-of-accounts.md for why each account is there. Numbers and names
come from the standard file (app/standard_chart.py), not from this module.
"""

from dataclasses import dataclass, field

from app.models.account import Account, AccountGroup, AccountType
from app.models.base import db
from app.models.organization import COMPANY_FORMS, Organization
from app.models.vat_code import VatCode
from app.standard_chart import (
    ACCOUNT,
    GROUP,
    HEADING,
    standard_accounts,
)

SOLE_PROPRIETORSHIP, APS = COMPANY_FORMS

# name: (normal balance, report type)
ACCOUNT_TYPES = {
    "Liability": ("credit", "balanceSheet"),
    "Asset": ("debit", "balanceSheet"),
    "Income": ("credit", "incomeStatement"),
    "Expense": ("debit", "incomeStatement"),
    "Equity": ("credit", "balanceSheet"),
}


@dataclass(frozen=True)
class StarterAccount:
    number: int
    type: str
    role: str | None = None
    # The company forms that get the account. None: all of them.
    forms: tuple[str, ...] | None = None
    # Only for our own accounts, which are not in the standard
    name: str | None = None
    standard_account: int | None = None
    is_bank: bool = False
    # The code (new name, see app/vat.py) a line on the account starts with.
    # A guess at the usual treatment, to be checked with the accountant: the
    # official list has no such default (docs/chart-of-accounts.md).
    vat: str | None = None


A = StarterAccount

STARTER_ACCOUNTS = (
    # Income
    A(1010, "Income", "sales", vat="S01"),
    A(1050, "Income", "sales_eu_goods", vat="S21"),
    A(1100, "Income", "sales_non_eu_goods", vat="S41"),
    A(1150, "Income", "sales_eu_services", vat="S23"),
    A(1200, "Income", "sales_non_eu_services", vat="S42"),
    A(1210, "Income", vat="S01"),
    A(1250, "Income", vat="S01"),
    A(3470, "Income"),
    A(3490, "Income"),
    # Purchases and expenses
    A(1610, "Expense", "purchases", vat="K010"),
    A(1630, "Expense", vat="K210"),
    A(1650, "Expense"),
    A(1710, "Expense", vat="K260"),
    A(1760, "Expense", vat="K010"),
    A(1850, "Expense", vat="K010"),
    A(1910, "Expense", vat="K070"),
    A(1930, "Expense", vat="K010"),
    A(2030, "Expense"),
    A(2230, "Expense", vat="K010"),
    A(2310, "Expense", vat="K010"),
    A(2370, "Expense", vat="K010"),
    A(2390, "Expense", vat="K030"),
    A(2410, "Expense", vat="K010"),
    A(2450, "Expense", vat="K010"),
    A(2470, "Expense"),
    A(2540, "Expense"),
    A(2650, "Expense"),
    A(2660, "Expense"),
    A(2670, "Expense", vat="K010"),
    A(2720, "Expense", "rounding"),
    A(2895, "Expense"),
    A(2896, "Expense", vat="K010"),
    A(3650, "Expense"),
    A(3670, "Expense"),
    A(3675, "Expense"),
    # Assets
    A(6190, "Asset", "receivables"),
    A(6320, "Asset", "vat_receivable"),
    A(6480, "Asset", "bank", is_bank=True),
    # SKAT's account is not in the standard: it is mapped to 6330 Øvrige
    # tilgodehavender (omsætningsaktiv)
    A(
        6481,
        "Asset",
        "tax_account",
        name="Skattekonto",
        standard_account=6330,
    ),
    # Liabilities and VAT
    A(7440, "Liability", "payables"),
    A(7680, "Liability", "output_vat"),
    A(7700, "Liability", "vat_eu_goods"),
    A(7720, "Liability", "vat_eu_services"),
    A(7740, "Liability", "input_vat"),
    A(7840, "Liability", "vat_payable"),
    # Equity of a sole proprietorship ("kun klasse A" in the standard)
    A(6915, "Equity", "owner_capital", forms=(SOLE_PROPRIETORSHIP,)),
    A(6916, "Equity", "annual_result", forms=(SOLE_PROPRIETORSHIP,)),
    A(6920, "Equity", forms=(SOLE_PROPRIETORSHIP,)),
    A(6921, "Equity", forms=(SOLE_PROPRIETORSHIP,)),
    A(6922, "Equity", forms=(SOLE_PROPRIETORSHIP,)),
    A(6923, "Equity", "owner_withdrawals", forms=(SOLE_PROPRIETORSHIP,)),
    A(6924, "Equity", "owner_deposits", forms=(SOLE_PROPRIETORSHIP,)),
    # Equity of an ApS
    A(6510, "Equity", "share_capital", forms=(APS,)),
    A(6520, "Equity", forms=(APS,)),
    A(6935, "Equity", forms=(APS,)),
    A(6940, "Equity", "retained_earnings", forms=(APS,)),
)


def starter_accounts(company_form: str) -> list[StarterAccount]:
    """The accounts a company form starts with."""
    if company_form not in COMPANY_FORMS:
        raise ValueError(f"Unknown company form: {company_form}")
    return [
        item
        for item in STARTER_ACCOUNTS
        if item.forms is None or company_form in item.forms
    ]


def standard_number(item: StarterAccount) -> int:
    """The account of the standard that the account stands for."""
    return item.standard_account or item.number


def group_of(item: StarterAccount) -> int:
    """The number of the standard group the account belongs to."""
    standard = standard_accounts()[standard_number(item)]
    if standard.kind != ACCOUNT or standard.group is None:
        raise ValueError(f"{standard.number} is not an account in a group")
    return standard.group


def group_interval(group_number: int) -> tuple[int, int]:
    """The numbers from the group up to the next heading or group."""
    headings = sorted(
        item.number
        for item in standard_accounts().values()
        if item.kind in (HEADING, GROUP)
    )
    later = [number for number in headings if number > group_number]
    return group_number, (later[0] - 1 if later else group_number)


@dataclass
class ChartResult:
    created: list[int] = field(default_factory=list)
    # An account with the number was there: it got its standard account and role
    adopted: list[int] = field(default_factory=list)
    unchanged: list[int] = field(default_factory=list)
    # number: why it was not added
    skipped: dict[int, str] = field(default_factory=dict)


def _account_type(organization: Organization, name: str) -> AccountType:
    found = AccountType.query.filter_by(
        organization_id=organization.id, name=name
    ).first()
    if found is None:
        normal_balance, report_type = ACCOUNT_TYPES[name]
        found = AccountType(
            organization_id=organization.id,
            name=name,
            normal_balance=normal_balance,
            report_type=report_type,
        )
        db.session.add(found)
        db.session.flush()
    return found


def _account_group(
    organization: Organization, account_type: AccountType, number: int
) -> AccountGroup:
    name = standard_accounts()[number].name
    found = AccountGroup.query.filter_by(
        organization_id=organization.id, number=number, name=name
    ).first()
    if found is None:
        start, end = group_interval(number)
        found = AccountGroup(
            organization_id=organization.id,
            account_type_id=account_type.id,
            name=name,
            number=number,
            interval_start=start,
            interval_end=end,
        )
        db.session.add(found)
        db.session.flush()
    return found


def apply_starter_chart(
    organization: Organization, commit: bool = True
) -> ChartResult:
    """Give the organization the starter accounts of its company form.

    Safe to run again. An account that already has the number is kept as it
    is, and gets its standard account, its role and its default VAT code if it
    has none. Nothing is ever deleted or renamed.
    """
    standard = standard_accounts()
    vat_code_ids = {code.code: code.id for code in VatCode.query}
    result = ChartResult()
    for item in starter_accounts(organization.company_form):
        number = item.number
        name = item.name or standard[standard_number(item)].name
        existing = Account.query.filter_by(
            organization_id=organization.id, number=number
        ).first()
        role_holder = (
            Account.query.filter_by(
                organization_id=organization.id, system_role=item.role
            ).first()
            if item.role
            else None
        )
        if role_holder is not None and role_holder is not existing:
            result.skipped[number] = (
                f"role {item.role} is held by account {role_holder.number}"
            )
            continue

        vat_code_id = vat_code_ids[item.vat] if item.vat else None
        if existing is not None:
            changed = False
            if existing.default_vat_code_id is None and vat_code_id:
                existing.default_vat_code_id = vat_code_id
                changed = True
            if existing.standard_account is None:
                existing.standard_account = standard_number(item)
                changed = True
            if existing.system_role is None and item.role:
                existing.system_role = item.role
                changed = True
            (result.adopted if changed else result.unchanged).append(number)
            continue

        if Account.query.filter_by(
            organization_id=organization.id, name=name
        ).first():
            result.skipped[number] = f"the name {name!r} is already used"
            continue

        account_type = _account_type(organization, item.type)
        group = _account_group(organization, account_type, group_of(item))
        db.session.add(
            Account(
                organization_id=organization.id,
                account_type_id=account_type.id,
                account_group_id=group.id,
                number=number,
                name=name,
                standard_account=standard_number(item),
                system_role=item.role,
                default_vat_code_id=vat_code_id,
                is_bank_account=item.is_bank,
                is_payment_enabled=item.is_bank,
                is_deposit=item.is_bank,
            )
        )
        db.session.flush()
        result.created.append(number)

    if commit:
        db.session.commit()
    else:
        db.session.flush()
    return result
