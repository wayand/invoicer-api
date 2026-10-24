from flask_marshmallow import Marshmallow
from marshmallow import fields, pre_load

from app.money import DecimalNumber

from .invoice import Invoice

ma = Marshmallow()

IGNORED_INPUT = {"amount", "vat_amount", "gross_amount", "excluding_vat"}


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

    @pre_load
    def drop_computed_fields(self, data, **kwargs):
        """The app used to send the totals (and excluding_vat, which nothing
        used). The server computes the totals, so whatever is sent is ignored."""
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if k not in IGNORED_INPUT}
        return data

    class Meta:
        model = Invoice
        include_fk = True


class InvoiceWithLinesSchema(InvoiceSchema):
    lines = fields.Nested("InvoiceLineSchema", many=True, required=True)


invoice_schema_with_lines = InvoiceWithLinesSchema()
invoices_schema = InvoiceSchema(many=True)
