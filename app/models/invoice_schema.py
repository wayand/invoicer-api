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


class InvoiceWithLinesSchema(InvoiceSchema):
    lines = fields.Nested("InvoiceLineSchema", many=True, required=True)
    # The VAT of each code on the invoice, as a Danish invoice shows it
    vat_by_code = fields.Function(_vat_by_code, dump_only=True)


class ApproveInputSchema(Schema):
    invoice_no = fields.String(
        allow_none=True, validate=validate.Length(max=100)
    )


approve_input_schema = ApproveInputSchema()
invoice_schema_with_lines = InvoiceWithLinesSchema()
invoices_schema = InvoiceSchema(many=True)
