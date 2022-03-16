from app.models import ma, Account, AccountGroup, AccountType, TaxRateSchema
from marshmallow import (
    fields,
    validate,
    post_dump
)

class AccountTypeSchema(ma.SQLAlchemyAutoSchema):
    class Meta:
        model = AccountType
        include_fk = True

class AccountGroupSchema(ma.SQLAlchemyAutoSchema):
    class Meta:
        model = AccountGroup
        include_fk = True

class BaseAccountSchema(ma.SQLAlchemySchema):
    id = fields.Integer(dump_only=True)
    number = fields.Integer()
    organization_id = fields.Integer()
    account_type_id = fields.Integer()
    account_group_id = fields.Integer()
    name = fields.String(required=True, validate=[validate.Length(min=1, max=100)])
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)

    class Meta:
        model = Account
        include_fk = True

class DepositAccountSchema(BaseAccountSchema):
    is_bank_account = fields.Boolean()
    is_payment_enabled = fields.Boolean()
    bank_account_number = fields.Integer()
    bank_registration_number = fields.Integer()
    bank_iban_number = fields.Str()
    bank_swift_number = fields.Str()
    bank_id = fields.Integer(allow_none=True)
    is_deposit = fields.Boolean()

class AccountSchema(BaseAccountSchema):
    tax_rate_id = fields.Integer(allow_none=True)
    description =  fields.Str()
    currency_id = fields.Str()
    is_archived = fields.Boolean()
    is_deposit = fields.Boolean()
    is_bank_account = fields.Boolean()
    is_payment_enabled = fields.Boolean()
    bank_account_number = fields.Integer()
    bank_registration_number = fields.Integer()
    bank_iban_number = fields.Str()
    bank_swift_number = fields.Str()
    bank_id = fields.Integer(allow_none=True)

    account_group = fields.Nested('AccountGroupSchema', dump_only=True)
    account_type = fields.Nested('AccountTypeSchema', dump_only=True)
    tax_rate = fields.Nested('TaxRateSchema', dump_only=True)


account_schema = AccountSchema()
accounts_schema = AccountSchema(many=True)
account_groups_schema = AccountGroupSchema(many=True)