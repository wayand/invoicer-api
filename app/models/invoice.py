from .base import BaseModel, db

STATES = ("draft", "approved")


class Invoice(BaseModel):
    __tablename__ = "invoices"
    __table_args__ = (
        # The number is taken when the invoice is approved (a draft in
        # sequential mode has none), and is never used twice. A null does not
        # collide with another null.
        db.UniqueConstraint(
            "organization_id", "invoice_no", name="uq_invoices_org_no"
        ),
        db.CheckConstraint(
            "state IN ('draft', 'approved')", name="ck_invoices_state"
        ),
        # An approved invoice has its number and its voucher, and says when
        # and by whom: the posting service sets them together
        db.CheckConstraint(
            "(state = 'approved') = (invoice_no IS NOT NULL "
            "AND journal_entry_id IS NOT NULL AND approved_at IS NOT NULL "
            "AND approved_by IS NOT NULL)",
            name="ck_invoices_approved",
        ),
    )

    id_seq = db.Sequence(__tablename__ + "_id_seq")

    id = db.Column(
        db.Integer,
        id_seq,
        server_default=id_seq.next_value(),
        autoincrement=True,
        primary_key=True,
        nullable=False,
    )

    organization_id = db.Column(
        db.Integer,
        db.ForeignKey("organizations.id"),
        nullable=False,
    )
    # Null for a draft in sequential mode: the number comes with the approval
    invoice_no = db.Column(db.String(100), nullable=True)

    contact_id = db.Column(
        db.Integer, db.ForeignKey("contacts.id"), nullable=False
    )
    invoice_date = db.Column(db.Date, default=None, nullable=False)
    duedate = db.Column(db.Date, default=None, nullable=False)
    amount = db.Column(
        db.Numeric(14, 2), server_default="0.00", default=0.00, nullable=False
    )
    gross_amount = db.Column(
        db.Numeric(14, 2), server_default="0.00", default=0.00, nullable=False
    )
    vat_amount = db.Column(
        db.Numeric(14, 2), server_default="0.00", default=0.00, nullable=False
    )
    is_sent = db.Column(
        db.Boolean,
        server_default=db.text("false"),
        default=False,
        nullable=False,
    )
    state = db.Column(
        db.String(20), server_default="draft", default="draft", nullable=False
    )
    currency_id = db.Column(
        db.String(11), server_default="DKK", default="DKK", nullable=False
    )
    template_id = db.Column(
        db.String(100), server_default="1", default="1", nullable=False
    )
    # The voucher an approved invoice was posted as (docs/invoice-posting-design.md)
    journal_entry_id = db.Column(
        db.Integer,
        db.ForeignKey("journal_entries.id"),
        unique=True,
        nullable=True,
    )
    approved_at = db.Column(db.DateTime, nullable=True)
    approved_by = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=True
    )

    contact = db.relationship("Contact", backref="invoices")
    journal_entry = db.relationship("JournalEntry", viewonly=True)
    lines = db.relationship(
        "InvoiceLine", backref="invoices", cascade="all, delete"
    )

    def __repr__(self):
        return "<Invoice {}, lines{}>".format(self.id, self.lines)
