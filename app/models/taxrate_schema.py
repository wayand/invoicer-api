from app.models import ma, TaxRate
from marshmallow import (
    fields,
    validate,
    post_dump
)

class TaxRateSchema(ma.SQLAlchemySchema):
    id = fields.Integer(dump_only=True)
    organization_id = fields.Integer()
    name = fields.String(required=True, validate=[validate.Length(min=1, max=100)])
    abbreviation = fields.String(required=True)
    applies_to_purchases = fields.Boolean()
    applies_to_sales = fields.Boolean()
    description = fields.String()
    is_active = fields.Boolean()
    is_predefined = fields.Boolean()
    net_amount_meta_field_id = fields.Integer()
    predefined_tag = fields.String()
    rate = fields.Decimal(required=True)
    tax_rate_group = fields.String()

    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)

    @post_dump()
    def convert_decimal(self, data, many):
        data['rate'] = float(data.get('rate')) if data.get('rate') else None
        return data

    class Meta:
        model = TaxRate
        include_fk = True

taxrate_schema = TaxRateSchema()
taxrates_schema = TaxRateSchema(many=True)