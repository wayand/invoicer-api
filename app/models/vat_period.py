"""A settled VAT period (docs/vat-design.md, section 8).

One row for each period that has been settled: the settlement posts the
voucher that moves the VAT accounts to the VAT payable (or receivable) account,
and this row records it. The figures are not stored: they come from the ledger,
and the lock on a settled period keeps them unchanged.
"""

from datetime import datetime

from .base import db

PERIOD_TYPES = ("half_year", "quarter", "month")
# The source_type of the voucher that settles a period
SETTLEMENT = "vat_settlement"
STATUSES = ("settled", "filed")


class VatPeriod(db.Model):
    __tablename__ = "vat_periods"
    __table_args__ = (
        db.UniqueConstraint(
            "organization_id", "start_date", name="uq_vat_periods_org_start"
        ),
        db.CheckConstraint(
            "end_date >= start_date", name="ck_vat_periods_dates"
        ),
        db.CheckConstraint(
            "period_type IN ('half_year', 'quarter', 'month')",
            name="ck_vat_periods_type",
        ),
        db.CheckConstraint(
            "status IN ('settled', 'filed')", name="ck_vat_periods_status"
        ),
        # A filed period says when, and by whom
        db.CheckConstraint(
            "(status = 'filed') = (filed_on IS NOT NULL AND filed_by IS NOT NULL)",
            name="ck_vat_periods_filed",
        ),
        db.Index("ix_vat_periods_org_end", "organization_id", "end_date"),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    organization_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"), nullable=False
    )
    # The type the organization had when the period was settled
    period_type = db.Column(db.String(10), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    # When the return and the payment are due. Calculated, and can be
    # corrected: holidays are not known to the program.
    due_date = db.Column(db.Date, nullable=False)
    status = db.Column(
        db.String(10),
        server_default="settled",
        default="settled",
        nullable=False,
    )
    # The voucher of the settlement. Null when there was nothing to move: a
    # period with only sales and purchases without VAT.
    settlement_entry_id = db.Column(
        db.Integer, db.ForeignKey("journal_entries.id"), nullable=True
    )
    settled_at = db.Column(db.DateTime, default=datetime.now, nullable=False)
    settled_by = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False
    )
    # The day the return was filed in TastSelv Erhverv, as the user gives it
    filed_on = db.Column(db.Date, nullable=True)
    filed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    reference = db.Column(db.String(100), nullable=True)

    settlement_entry = db.relationship("JournalEntry", viewonly=True)

    def __repr__(self):
        return f"<VatPeriod {self.start_date} to {self.end_date}>"
