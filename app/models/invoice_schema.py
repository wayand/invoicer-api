from flask_marshmallow import Marshmallow
from marshmallow import fields

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


class InvoiceWithLinesSchema(InvoiceSchema):
    lines = fields.Nested("InvoiceLineSchema", many=True, required=True)


invoice_schema_with_lines = InvoiceWithLinesSchema()
invoices_schema = InvoiceSchema(many=True)
