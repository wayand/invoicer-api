from app.models import ma, User
from marshmallow import (
    INCLUDE,
    fields,
    validate,
    post_dump
)

class UserBaseSchema(ma.SQLAlchemySchema):
    id = fields.Int(dump_only=True, strict=True)
    organization_id = fields.Integer(required=False)
    email = fields.Email(required=False)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
    class Meta:
        model = User
        include_fk = True

class UserEmailSchema(UserBaseSchema):
    email = fields.Email(required=False)

class ResetPasswordSchema(UserBaseSchema):
    new_password = fields.String(required=True, load_only=True, validate=validate.Length(min=8))
    reset_code = fields.String(required=True, load_only=True)

class UserTokenSchema(UserBaseSchema):
    password_hash = fields.String(required=True, load_only=True, data_key="password")
    is_two_factor_auth = fields.Boolean(dump_only=True)
    class Meta:
        unknown = INCLUDE

class UserChangePasswordSchema(UserBaseSchema):
    password_hash = fields.String(required=True, load_only=True, data_key="password")
    new_password = fields.String(required=True, load_only=True, validate=validate.Length(min=8))

class UserTOTPSetupSchema(UserBaseSchema):
    password_hash = fields.String(required=True, load_only=True, data_key="password")
    totp_code = fields.String(required=True, load_only=True, validate=validate.Length(min=6, max=6))

class UserTOTPSetupDeleteSchema(UserBaseSchema):
    password_hash = fields.String(required=True, load_only=True, data_key="password")

class UserSchema(UserBaseSchema):
    name = fields.String(required=True, validate=[validate.Length(min=1, max=100)])
    owner = fields.Boolean(required=True)
    is_two_factor_auth = fields.Boolean(required=True)
    two_factor_auth_type = fields.String(required=True)

reset_password_schema = ResetPasswordSchema()
userchangepassword_schema = UserChangePasswordSchema()
usertotpsetup_schema = UserTOTPSetupSchema()
usertotpsetupdelete_schema = UserTOTPSetupDeleteSchema()
usertoken_schema = UserTokenSchema()
useremail_schema = UserEmailSchema()
user_schema = UserSchema()
users_schema = UserSchema(many=True)