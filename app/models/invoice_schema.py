from decimal import Decimal

from flask_marshmallow import Marshmallow
from marshmallow import Schema, fields, validate

from app.invoice_vat import vat_summary
from app.money import DecimalNumber

from .invoice import Invoice

ma = Marshmallow()


class InvoiceSchema(ma.SQLAlchemySchema):
    id = fields.Int(dump_only=True)
    organization_id = fields.Int(required=True)
    contact_id = fields.Int(required=True)
    # Null for a draft in sequential mode: the number comes with the approval
    invoice_no = fields.Str(allow_none=True, validate=validate.Length(max=100))
    currency_id = fields.Str(required=True)
    # An invoice, or a credit note that refers to the invoice it corrects
    kind = fields.String(dump_only=True)
    credits_invoice_id = fields.Int(dump_only=True, allow_none=True)
    # What the server does with an invoice: the client cannot set them
    is_sent = fields.Boolean(dump_only=True)
    state = fields.String(dump_only=True)
    journal_entry_id = fields.Int(dump_only=True, allow_none=True)
    voucher_no = fields.Function(
        lambda invoice: (
            invoice.journal_entry.voucher_no if invoice.journal_entry else None
        ),
        dump_only=True,
        allow_none=True,
    )
    approved_at = fields.DateTime(dump_only=True, allow_none=True)
    approved_by = fields.Int(dump_only=True, allow_none=True)
    template_id = fields.Str()
    invoice_date = fields.Date()  # format='%Y-%m-%d'
    duedate = fields.Date()  # format='%Y-%m-%d'
    # Computed by the server from the lines (docs/money-rules.md)
    amount = DecimalNumber(places=2, dump_only=True)
    vat_amount = DecimalNumber(places=2, dump_only=True)
    gross_amount = DecimalNumber(places=2, dump_only=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
    contact = fields.Nested(
        "ContactSchema", dump_only=True, many=False, required=False
    )
    payment_methods = fields.Nested(
        "PaymentMethodSchema", dump_only=True, many=True, required=True
    )

    class Meta:
        model = Invoice
        include_fk = True


def _vat_by_code(invoice):
    return [
        {
            "code": item.code,
            "rate": float(item.rate),
            "base": float(item.base),
            "vat": float(item.vat),
        }
        for item in vat_summary(invoice)
    ]


def _credit_notes(invoice):
    return [
        {
            "id": note.id,
            "invoice_no": note.invoice_no,
            "state": note.state,
            "invoice_date": note.invoice_date.isoformat(),
            "gross_amount": float(note.gross_amount),
        }
        for note in invoice.credit_notes
    ]


class InvoiceWithLinesSchema(InvoiceSchema):
    lines = fields.Nested("InvoiceLineSchema", many=True, required=True)
    # The number of the invoice a credit note corrects
    credits_invoice_no = fields.Function(
        lambda invoice: (
            invoice.credits_invoice.invoice_no
            if invoice.credits_invoice
            else None
        ),
        dump_only=True,
        allow_none=True,
    )
    # The credit notes of an invoice, and what the approved ones credit
    credit_notes = fields.Function(_credit_notes, dump_only=True)
    credited_amount = fields.Function(
        lambda invoice: float(
            sum(
                (
                    note.gross_amount
                    for note in invoice.credit_notes
                    if note.state == "approved"
                ),
                Decimal("0.00"),
            )
        ),
        dump_only=True,
    )
    # The VAT of each code on the invoice, as a Danish invoice shows it
    vat_by_code = fields.Function(_vat_by_code, dump_only=True)


class ApproveInputSchema(Schema):
    invoice_no = fields.String(
        allow_none=True, validate=validate.Length(max=100)
    )


approve_input_schema = ApproveInputSchema()
invoice_schema_with_lines = InvoiceWithLinesSchema()
invoices_schema = InvoiceSchema(many=True)
