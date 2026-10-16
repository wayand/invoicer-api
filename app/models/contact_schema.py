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
    # The optional text columns are nullable and come back as null when never
    # filled in, so null must be accepted when a form sends the contact back.
    logo = fields.String(allow_none=True)
    registration_no = fields.String()  # part of the primary key: never null
    type = fields.String()
    is_company = fields.Boolean()
    phone = fields.String(allow_none=True)
    street = fields.String(allow_none=True)
    zipcode = fields.String(allow_none=True)
    city = fields.String(allow_none=True)
    email = fields.Email(required=True)
    archived = fields.Boolean()
    contactperson_name = fields.String(allow_none=True)
    contactperson_email = fields.Email(required=False, allow_none=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)

    class Meta:
        model = Contact
        include_fk = True


contact_schema = ContactSchema()
contacts_schema = ContactSchema(many=True)
