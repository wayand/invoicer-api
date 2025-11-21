from flask_marshmallow import Marshmallow
from marshmallow import (
    ValidationError,
    fields,
    post_dump,
    pre_load,
    validate,
)

from .invoiceline import InvoiceLine

ma = Marshmallow()

# def validate_amount(amount):
#     if amount:
#         raise ValidationError(f"Amount type is: {amount} {type(amount)}")


class InvoiceLineSchema(ma.SQLAlchemySchema):
    id = fields.Integer()
    product_id = fields.Integer(required=True)
    invoice_id = fields.Integer(required=False)
    quantity = fields.Decimal(required=True, places=2)
    amount = fields.Decimal(required=True, places=2)
    unit_price = fields.Decimal(required=True, places=2)
    description = fields.String(
        required=True, validate=[validate.Length(min=2, max=100)]
    )
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)

    @pre_load
    def check_line_quantity(self, data, **kwargs):
        check_quantity = isinstance(data.get("quantity"), (float, int))
        if not check_quantity:
            raise ValidationError(
                "Invalid type. Expected Number but got String.", "quantity"
            )
        return data

    @pre_load
    def check_line_amount_type(self, data, **kwargs):
        check_amount_type = isinstance(data.get("amount"), (float, int))
        if not check_amount_type:
            raise ValidationError(
                "Invalid type. Expected Number but got String.", "amount"
            )
        return data

    @pre_load
    def check_line_unit_price_type(self, data, **kwargs):
        check_unit_price_type = isinstance(data.get("unit_price"), (float, int))
        if not check_unit_price_type:
            raise ValidationError(
                "Invalid type. Expected Number but got String.", "unit_price"
            )
        return data

    @post_dump()
    def convert_decimal(self, data, many, **kwargs):
        data["quantity"] = (
            float(data.get("quantity")) if data.get("quantity") >= 0 else None
        )
        data["amount"] = (
            float(data.get("amount")) if data.get("amount") >= 0 else None
        )
        data["unit_price"] = (
            float(data.get("unit_price"))
            if data.get("unit_price") >= 0
            else None
        )
        return data

    class Meta:
        model = InvoiceLine
        include_fk = True


invoiceline_schema = InvoiceLineSchema()
invoicelines_schema = InvoiceLineSchema(many=True)
