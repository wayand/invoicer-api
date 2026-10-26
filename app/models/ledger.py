"""The ledger: fiscal years and the journal (docs/ledger-design.md).

Posted entries cannot be changed or deleted, and every entry balances. Both
are enforced by triggers that the migration creates, so no code path can
break them by accident. A mistake is corrected with a reversing entry.
"""

from datetime import datetime

from sqlalchemy.orm import Mapped, relationship

from .account import Account
from .base import BaseModel, db

FISCAL_YEAR_STATUSES = ("open", "closed")


class FiscalYear(BaseModel):
    __tablename__ = "fiscal_years"
    __table_args__ = (
        db.UniqueConstraint(
            "organization_id", "start_date", name="uq_fiscal_years_org_start"
        ),
        # Lets a journal entry refer to (id, organization_id)
        db.UniqueConstraint(
            "id", "organization_id", name="uq_fiscal_years_id_org"
        ),
        db.CheckConstraint(
            "end_date >= start_date", name="ck_fiscal_years_dates"
        ),
        db.CheckConstraint(
            "status IN ('open', 'closed')", name="ck_fiscal_years_status"
        ),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    organization_id = db.Column(
        db.Integer,
        db.ForeignKey("organizations.id"),
        nullable=False,
    )
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    status = db.Column(
        db.String(10), server_default="open", default="open", nullable=False
    )


class LedgerCounter(db.Model):
    """The next voucher number of an organization. The posting service locks
    the row, takes the number and writes the entry in one transaction, so a
    failed posting does not use up a number."""

    __tablename__ = "ledger_counters"

    organization_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"), primary_key=True
    )
    next_voucher_no = db.Column(
        db.Integer, server_default="1", default=1, nullable=False
    )


class JournalEntry(db.Model):
    """A voucher. Never updated or deleted, so there is no updated_at."""

    __tablename__ = "journal_entries"
    __table_args__ = (
        # One running sequence per organization: no restart, no gap
        db.UniqueConstraint(
            "organization_id", "voucher_no", name="uq_journal_entries_voucher"
        ),
        # Lets a journal line refer to (id, organization_id)
        db.UniqueConstraint(
            "id", "organization_id", name="uq_journal_entries_id_org"
        ),
        db.ForeignKeyConstraint(
            ["fiscal_year_id", "organization_id"],
            ["fiscal_years.id", "fiscal_years.organization_id"],
            name="fk_journal_entries_fiscal_year_org",
        ),
        db.CheckConstraint("voucher_no >= 1", name="ck_journal_entries_no"),
        db.CheckConstraint(
            "reverses_entry_id IS NULL OR reverses_entry_id <> id",
            name="ck_journal_entries_reverses_other",
        ),
        db.Index(
            "ix_journal_entries_org_date", "organization_id", "entry_date"
        ),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    organization_id = db.Column(
        db.Integer,
        db.ForeignKey("organizations.id"),
        nullable=False,
    )
    fiscal_year_id = db.Column(db.Integer, nullable=False)
    voucher_no = db.Column(db.Integer, nullable=False)
    entry_date = db.Column(db.Date, nullable=False)
    description = db.Column(db.String(255), nullable=False)
    # What produced the entry: "manual" now, later "invoice", "payment", ...
    source_type = db.Column(
        db.String(30), server_default="manual", default="manual", nullable=False
    )
    source_id = db.Column(db.Integer, nullable=True)
    # The entry this one reverses. Unique: an entry is reversed once.
    reverses_entry_id = db.Column(
        db.Integer,
        db.ForeignKey("journal_entries.id"),
        unique=True,
        nullable=True,
    )
    created_by = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False
    )
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)
    # The transaction that posted the entry. A line can only be added in that
    # same transaction, so an entry cannot grow after it was posted.
    created_txid = db.Column(
        db.BigInteger, server_default=db.text("txid_current()"), nullable=False
    )

    lines: Mapped[list["JournalLine"]] = relationship(
        "JournalLine",
        back_populates="entry",
        order_by="JournalLine.line_no",
    )


class JournalLine(db.Model):
    """One side of an entry: a debit or a credit, never both."""

    __tablename__ = "journal_lines"
    __table_args__ = (
        db.UniqueConstraint(
            "journal_entry_id", "line_no", name="uq_journal_lines_no"
        ),
        db.ForeignKeyConstraint(
            ["journal_entry_id", "organization_id"],
            ["journal_entries.id", "journal_entries.organization_id"],
            name="fk_journal_lines_entry_org",
        ),
        db.ForeignKeyConstraint(
            ["account_id", "organization_id"],
            ["accounts.id", "accounts.organization_id"],
            name="fk_journal_lines_account_org",
        ),
        db.CheckConstraint("line_no >= 1", name="ck_journal_lines_no"),
        db.CheckConstraint(
            "(debit > 0 AND credit = 0) OR (credit > 0 AND debit = 0)",
            name="ck_journal_lines_one_side",
        ),
        db.Index("ix_journal_lines_account", "account_id"),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    journal_entry_id = db.Column(db.Integer, nullable=False)
    organization_id = db.Column(
        db.Integer,
        db.ForeignKey("organizations.id"),
        nullable=False,
    )
    line_no = db.Column(db.Integer, nullable=False)
    account_id = db.Column(db.Integer, nullable=False)
    # Amounts follow docs/money-rules.md: 2 decimals, in DKK
    debit = db.Column(
        db.Numeric(14, 2), server_default="0", default=0, nullable=False
    )
    credit = db.Column(
        db.Numeric(14, 2), server_default="0", default=0, nullable=False
    )
    description = db.Column(db.String(255), nullable=True)
    # The customer or supplier the line is for
    contact_id = db.Column(
        db.Integer, db.ForeignKey("contacts.id"), nullable=True
    )

    entry: Mapped["JournalEntry"] = relationship(
        "JournalEntry", back_populates="lines"
    )
    account: Mapped[Account] = relationship(
        "Account",
        primaryjoin="and_(JournalLine.account_id == Account.id, "
        "JournalLine.organization_id == Account.organization_id)",
        foreign_keys=[account_id, organization_id],
        viewonly=True,
    )
