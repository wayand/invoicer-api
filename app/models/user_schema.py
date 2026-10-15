from flask_marshmallow import Marshmallow
from marshmallow import INCLUDE, fields, pre_load, validate

from .user import User

ma = Marshmallow()


class UserBaseSchema(ma.SQLAlchemySchema):
    id = fields.Int(dump_only=True)
    organization_id = fields.Integer(required=False)
    email = fields.Email(required=False)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)

    @pre_load
    def normalize_email(self, data, **kwargs):
        """Strip and lowercase the address before it is validated."""
        email = data.get("email") if isinstance(data, dict) else None
        if isinstance(email, str):
            data = {**data, "email": User.normalize_email(email)}
        return data

    class Meta:
        model = User
        include_fk = True


class UserEmailSchema(UserBaseSchema):
    email = fields.Email(required=False)


class ResetPasswordSchema(UserBaseSchema):
    new_password = fields.String(
        required=True, load_only=True, validate=validate.Length(min=8)
    )
    reset_code = fields.String(required=True, load_only=True)


class UserTokenSchema(UserBaseSchema):
    password_hash = fields.String(
        required=True, load_only=True, data_key="password"
    )
    is_two_factor_auth = fields.Boolean(dump_only=True)

    class Meta:
        unknown = INCLUDE


class UserChangePasswordSchema(UserBaseSchema):
    password_hash = fields.String(
        required=True, load_only=True, data_key="password"
    )
    new_password = fields.String(
        required=True, load_only=True, validate=validate.Length(min=8)
    )


class UserTOTPSetupSchema(UserBaseSchema):
    password_hash = fields.String(
        required=True, load_only=True, data_key="password"
    )
    totp_code = fields.String(
        required=True, load_only=True, validate=validate.Length(min=6, max=6)
    )


class UserTOTPSetupDeleteSchema(UserBaseSchema):
    password_hash = fields.String(
        required=True, load_only=True, data_key="password"
    )


class UserPasswordSchema(UserBaseSchema):
    password_hash = fields.String(
        required=True, load_only=True, data_key="password"
    )


class UserSchema(UserBaseSchema):
    name = fields.String(
        required=True, validate=[validate.Length(min=1, max=100)]
    )
    owner = fields.Boolean(required=True)
    is_two_factor_auth = fields.Boolean(required=True)
    two_factor_auth_type = fields.String(required=True)


reset_password_schema = ResetPasswordSchema()
userchangepassword_schema = UserChangePasswordSchema()
usertotpsetup_schema = UserTOTPSetupSchema()
usertotpsetupdelete_schema = UserTOTPSetupDeleteSchema()
userpassword_schema = UserPasswordSchema()
usertoken_schema = UserTokenSchema()
useremail_schema = UserEmailSchema()
user_schema = UserSchema()
users_schema = UserSchema(many=True)
