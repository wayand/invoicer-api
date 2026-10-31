from flask_marshmallow import Marshmallow
from marshmallow import (
    ValidationError,
    fields,
    pre_load,
    validate,
)

from app.money import MAX_FACTOR, DecimalNumber

from .invoiceline import InvoiceLine

ma = Marshmallow()

# def validate_amount(amount):
#     if amount:
#         raise ValidationError(f"Amount type is: {amount} {type(amount)}")


def _vat_code(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 10:
        raise ValidationError("Expected a VAT code such as S01.")
    return value


class InvoiceLineSchema(ma.SQLAlchemySchema):
    id = fields.Integer()
    product_id = fields.Integer(required=True)
    invoice_id = fields.Integer(required=False)
    quantity = DecimalNumber(
        places=3,
        required=True,
        validate=validate.Range(min=-MAX_FACTOR, max=MAX_FACTOR),
    )
    unit_price = DecimalNumber(
        places=3,
        required=True,
        validate=validate.Range(min=-MAX_FACTOR, max=MAX_FACTOR),
    )
    # Computed by the server: quantity x unit price (docs/money-rules.md)
    amount = DecimalNumber(places=2, dump_only=True)
    description = fields.String(
        required=True, validate=[validate.Length(min=2, max=100)]
    )
    # A sales code such as S01 (docs/vat-design.md, section 7). The route
    # checks that it can be used on an invoice.
    vat_code = fields.Function(
        serialize=lambda line: line.vat_code.code,
        deserialize=lambda value: _vat_code(value),
        required=True,
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
    def check_line_unit_price_type(self, data, **kwargs):
        check_unit_price_type = isinstance(data.get("unit_price"), (float, int))
        if not check_unit_price_type:
            raise ValidationError(
                "Invalid type. Expected Number but got String.", "unit_price"
            )
        return data

    class Meta:
        model = InvoiceLine
        include_fk = True


invoiceline_schema = InvoiceLineSchema()
invoicelines_schema = InvoiceLineSchema(many=True)
