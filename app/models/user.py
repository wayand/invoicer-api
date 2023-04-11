from app.models import db, BaseModel
from passlib.hash import pbkdf2_sha256 as sha256
import os, base64, onetimepass
from flask import current_app
import urllib.parse
from time import time
import jwt


class User(BaseModel):
    __tablename__ = "users"

    id_seq = db.Sequence(__tablename__ + "_id_seq")

    id = db.Column(
        db.Integer,
        id_seq,
        server_default=id_seq.next_value(),
        autoincrement=True,
        primary_key=False,
        unique=True,
        nullable=False,
    )

    """
    Primary keys: organization_id, email
    """

    organization_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"), primary_key=True, nullable=False
    )
    email = db.Column(db.String(120), primary_key=True, nullable=False)
    email_is_confirmed = db.Column(db.Boolean, nullable=False, default=False)
    email_confirmed_on = db.Column(db.DateTime, nullable=True)

    name = db.Column(db.String(64), nullable=False)
    owner = db.Column(
        db.Boolean, server_default=db.text("false"), default=False, nullable=False
    )
    password_hash = db.Column(db.String(128), nullable=False)
    is_two_factor_auth = db.Column(
        db.Boolean, server_default=db.text("true"), default=True, nullable=False
    )
    two_factor_auth_type = db.Column(
        db.String(50),
        default="2fa_otp_email",
        server_default="2fa_otp_email",
        nullable=True,
    )
    otp_secret = db.Column(db.String(16), nullable=False)
    otp_secret_temp = db.Column(db.String(16), nullable=False)

    def __repr__(self):
        return f"<User {self.name}>"

    @staticmethod
    def generate_hash(password):
        return sha256.hash(password)

    @staticmethod
    def verify_hash(password, hash_):
        return sha256.verify(password, hash_)

    def get_totp_uri(self):
        return f"otpauth://totp/invoicer-app:{urllib.parse.quote(self.email)}?secret={self.otp_secret_temp}&issuer=invoicer-app"

    @staticmethod
    def generate_otp_secret():
        return base64.b32encode(os.urandom(10)).decode("utf-8")

    def get_totp_code(self, expire_in_sec=30):
        """param expire_in_sec: length of TOTP interval (30 seconds by default)"""
        return onetimepass.get_totp(self.otp_secret, interval_length=expire_in_sec)

    def verify_totp(self, token, expire_in_sec=30):
        return onetimepass.valid_totp(
            token, self.otp_secret, interval_length=expire_in_sec
        )

    def verify_totp_temp(self, token):
        return onetimepass.valid_totp(token, self.otp_secret_temp)

    ##### Password reset ########
    def get_reset_password_token(self, expires_in=3600):
        return jwt.encode(
            {"reset_password": self.id, "exp": time() + expires_in},
            current_app.config["JWT_SECRET_KEY"],
            algorithm="HS256",
        )

    @staticmethod
    def verify_reset_password_token(token):
        try:
            id = jwt.decode(
                token, current_app.config["JWT_SECRET_KEY"], algorithms=["HS256"]
            )["reset_password"]
        except Exception as e:
            print("reset_password_verify_error", e)
        return User.query.get(id)
