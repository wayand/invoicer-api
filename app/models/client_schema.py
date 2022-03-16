from app.models import ma, Client
from marshmallow import (
    fields,
    validate,
    post_dump
)

class ClientSchema(ma.SQLAlchemySchema):
    id = fields.Integer(dump_only=True)
    organization_id = fields.Integer()
    country_id = fields.Integer()
    name = fields.String(required=True, validate=[validate.Length(min=1, max=100)])
    logo = fields.String()
    registration_no = fields.String()
    type = fields.String()
    phone = fields.String()
    street = fields.String()
    zipcode = fields.String()
    city = fields.String()
    email = fields.Email(required=True)
    archived = fields.Boolean()
    contactperson_name = fields.String()
    contactperson_email = fields.Email(required=False)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)

    # @post_dump
    # def convert_decimal(self, data, many, **kwargs):
    #     data['amount'] = float(data.get('amount'))
    #     data['gross_amount'] = float(data.get('gross_amount'))
    #     data['vat_amount'] = float(data.get('vat_amount'))
    #     return data
    
    class Meta:
        model = Client
        include_fk = True

client_schema = ClientSchema()
clients_schema = ClientSchema(many=True)