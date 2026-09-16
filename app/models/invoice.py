from .base import BaseModel, db


class Invoice(BaseModel):
    __tablename__ = "invoices"

    id_seq = db.Sequence(__tablename__ + "_id_seq")

    id = db.Column(
        db.Integer,
        id_seq,
        server_default=id_seq.next_value(),
        autoincrement=True,
        primary_key=False,
        unique=True,
        nullable=False,
    )

    """
    Primary keys: organization_id, invoice_no
    """

    organization_id = db.Column(
        db.Integer,
        db.ForeignKey("organizations.id"),
        primary_key=True,
        nullable=False,
    )
    invoice_no = db.Column(db.String(100), primary_key=True, nullable=False)

    contact_id = db.Column(
        db.Integer, db.ForeignKey("contacts.id"), nullable=False
    )
    invoice_date = db.Column(db.Date, default=None, nullable=False)
    duedate = db.Column(db.Date, default=None, nullable=False)
    amount = db.Column(
        db.Numeric(10, 3), server_default="0.00", default=0.00, nullable=False
    )
    gross_amount = db.Column(
        db.Numeric(10, 3), server_default="0.00", default=0.00, nullable=False
    )
    vat_amount = db.Column(
        db.Numeric(10, 3), server_default="0.00", default=0.00, nullable=False
    )
    is_paid = db.Column(
        db.Boolean,
        server_default=db.text("false"),
        default=False,
        nullable=False,
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
    excluding_vat = db.Column(
        db.Boolean, server_default=db.text("true"), default=True, nullable=False
    )

    contact = db.relationship("Contact", backref="invoices")
    lines = db.relationship(
        "InvoiceLine", backref="invoices", cascade="all, delete"
    )

    def __repr__(self):
        return "<Invoice {}, lines{}>".format(self.id, self.lines)
