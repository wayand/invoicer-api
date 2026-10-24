from flask_marshmallow import Marshmallow
from marshmallow import fields, validate

from app.money import MAX_FACTOR, DecimalNumber

from .product import Product

ma = Marshmallow()


class ProductSchema(ma.SQLAlchemySchema):
    id = fields.Integer(dump_only=True)
    organization_id = fields.Integer()
    account_id = fields.Integer()
    name = fields.String(
        required=True, validate=[validate.Length(min=1, max=50)]
    )
    description = fields.String(
        required=True, validate=[validate.Length(min=2, max=100)]
    )
    unit_price = DecimalNumber(
        places=3,
        required=True,
        validate=validate.Range(min=-MAX_FACTOR, max=MAX_FACTOR),
    )
    archived = fields.Boolean(required=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
    account = fields.Nested("AccountSchema", dump_only=True)

    class Meta:
        model = Product
        include_fk = True


product_schema = ProductSchema()
products_schema = ProductSchema(many=True)
