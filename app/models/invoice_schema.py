from flask_marshmallow import Marshmallow
from marshmallow import ValidationError, fields, post_dump, pre_load

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
    excluding_vat = fields.Boolean()
    invoice_date = fields.Date()  # format='%Y-%m-%d'
    duedate = fields.Date()  # format='%Y-%m-%d'
    amount = fields.Decimal(required=True, places=2)
    vat_amount = fields.Decimal(required=True, places=2)
    gross_amount = fields.Decimal(required=True, places=2)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
    contact = fields.Nested(
        "ContactSchema", dump_only=True, many=False, required=False
    )
    payment_methods = fields.Nested(
        "PaymentMethodSchema", dump_only=True, many=True, required=True
    )

    @pre_load
    def check_amount_type(self, data, **kwargs):
        check_amount_type = isinstance(data.get("amount"), (float, int))
        if not check_amount_type:
            raise ValidationError(
                f"Invalid type. Expected Number but got String.({type(data.get('amount'))})",
                "amount",
            )
        return data

    @pre_load
    def check_gross_amount_type(self, data, **kwargs):
        check_gross_amount_type = isinstance(
            data.get("gross_amount"), (float, int)
        )
        if not check_gross_amount_type:
            raise ValidationError(
                "Invalid type. Expected Number but got String.", "gross_amount"
            )
        return data

    @pre_load
    def check_vat_amount_type(self, data, **kwargs):
        check_vat_amount_type = isinstance(data.get("amount"), (float, int))
        if not check_vat_amount_type:
            raise ValidationError(
                "Invalid type. Expected Number but got String.", "vat_amount"
            )
        return data

    @post_dump
    def convert_types(self, data, many, **kwargs):
        if data:
            data["amount"] = (
                float(data.get("amount")) if data.get("amount") >= 0 else None
            )
            data["gross_amount"] = (
                float(data.get("gross_amount"))
                if data.get("gross_amount") >= 0
                else None
            )
            data["vat_amount"] = (
                float(data.get("vat_amount"))
                if data.get("vat_amount") >= 0
                else None
            )
        return data

    class Meta:
        model = Invoice
        include_fk = True


class InvoiceWithLinesSchema(InvoiceSchema):
    lines = fields.Nested("InvoiceLineSchema", many=True, required=True)


invoice_schema_with_lines = InvoiceWithLinesSchema()
invoices_schema = InvoiceSchema(many=True)
