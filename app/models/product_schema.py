from app.models import ma, Product
from marshmallow import (
    fields,
    validate,
    post_dump
)

class ProductSchema(ma.SQLAlchemySchema):
    id = fields.Integer(dump_only=True)
    organization_id = fields.Integer()
    account_id = fields.Integer()
    name = fields.String(required=True, validate=[validate.Length(min=1, max=50)])
    description = fields.String(required=True, validate=[validate.Length(min=2, max=100)])
    unit_price = fields.Decimal(required=True, places=2)
    archived = fields.Boolean(required=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
    account = fields.Nested('AccountSchema', dump_only=True)

    @post_dump()
    def convert_decimal(self, data, many, **kwargs):
        data['unit_price'] = float(data.get('unit_price')) if data.get('unit_price') >= 0 else None
        return data
    
    class Meta:
        model = Product
        include_fk = True

product_schema = ProductSchema()
products_schema = ProductSchema(many=True)