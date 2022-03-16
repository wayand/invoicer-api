from app.models import ma, Organization
from marshmallow import (
    fields,
    validate,
    post_dump
)

class OrganizationSchema(ma.SQLAlchemySchema):
    id = fields.Integer(dump_only=True)
    registration_no = fields.String()
    slug = fields.String()
    email = fields.Email(required=True)
    name = fields.String(required=True, validate=[validate.Length(min=5, max=100)])
    logo = fields.String()
    phone = fields.String()
    street = fields.String()
    zipcode = fields.String()
    city = fields.String()
    country_id = fields.Integer(required=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
    
    invoice_setting = fields.Nested('InvoiceSettingSchema', required=False)
    country = fields.Nested('CountrySchema', required=False)
    users = fields.Nested('UserSchema', many=True, required=False)

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