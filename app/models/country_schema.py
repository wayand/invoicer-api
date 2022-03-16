import re
from app.models import ma, Country
from marshmallow import (
    fields,
    validate,
    post_dump
)

class CountrySchema(ma.SQLAlchemySchema):
    id = fields.Integer(dump_only=True)
    currency_id = fields.String(required=True)
    locale_id = fields.String(required=True)
    name = fields.String(required=True, validate=[validate.Length(min=1, max=100)])
    icon = fields.String(required=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)

    # @post_dump
    # def convert_decimal(self, data, many, **kwargs):
    #     data['amount'] = float(data.get('amount'))
    #     data['gross_amount'] = float(data.get('gross_amount'))
    #     data['vat_amount'] = float(data.get('vat_amount'))
    #     return data
    
    class Meta:
        model = Country
        include_fk = True

country_schema = CountrySchema()
countries_schema = CountrySchema(many=True)