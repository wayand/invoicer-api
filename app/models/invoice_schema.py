from flask_marshmallow import Marshmallow
from marshmallow import fields

from app.invoice_vat import vat_summary
from app.money import DecimalNumber

from .invoice import Invoice

ma = Marshmallow()


class InvoiceSchema(ma.SQLAlchemySchema):
    id = fields.Int(dump_only=True)
    organization_id = fields.Int(required=True)
    contact_id = fields.Int(required=True)
    invoice_no = fields.Str(required=True)
    currency_id = fields.Str(required=True)
    is_paid = fields.Boolean()
    is_sent = fields.Boolean()
    state = fields.String(required=True)
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


invoice_schema_with_lines = InvoiceWithLinesSchema()
invoices_schema = InvoiceSchema(many=True)
