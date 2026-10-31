from flask_marshmallow import Marshmallow
from marshmallow import fields, validate

from .organization import VAT_PERIOD_TYPES, Organization

ma = Marshmallow()


class OrganizationSchema(ma.SQLAlchemySchema):
    id = fields.Integer(dump_only=True)
    # The optional text columns are nullable and come back as null when never
    # filled in, so null must be accepted when the form sends them back.
    registration_no = fields.String(allow_none=True)
    slug = fields.String()
    email = fields.Email(required=True)
    name = fields.String(
        required=True, validate=[validate.Length(min=5, max=100)]
    )
    # Null: not VAT-registered
    vat_period_type = fields.String(
        allow_none=True, validate=validate.OneOf(VAT_PERIOD_TYPES)
    )
    logo = fields.String(allow_none=True)
    phone = fields.String(allow_none=True)
    street = fields.String(allow_none=True)
    zipcode = fields.String(allow_none=True)
    city = fields.String(allow_none=True)
    country_id = fields.Integer(required=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)

    invoice_setting = fields.Nested("InvoiceSettingSchema", required=False)
    country = fields.Nested("CountrySchema", required=False)
    users = fields.Nested("UserSchema", many=True, required=False)

    # @post_dump
    # def convert_decimal(self, data, many, **kwargs):
    #     data['amount'] = float(data.get('amount'))
    #     data['gross_amount'] = float(data.get('gross_amount'))
    #     data['vat_amount'] = float(data.get('vat_amount'))
    #     return data

    class Meta:
        model = Organization
        include_fk = True


organization_schema = OrganizationSchema()
organizations_schema = OrganizationSchema(many=True)
