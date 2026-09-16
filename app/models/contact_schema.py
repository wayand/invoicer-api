from flask_marshmallow import Marshmallow
from marshmallow import fields, validate

from .contact import Contact

ma = Marshmallow()


class ContactSchema(ma.SQLAlchemySchema):
    id = fields.Integer(dump_only=True)
    organization_id = fields.Integer()
    country_id = fields.Integer()
    name = fields.String(
        required=True, validate=[validate.Length(min=1, max=100)]
    )
    logo = fields.String()
    registration_no = fields.String()
    type = fields.String()
    is_company = fields.Boolean()
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

    class Meta:
        model = Contact
        include_fk = True


contact_schema = ContactSchema()
contacts_schema = ContactSchema(many=True)
