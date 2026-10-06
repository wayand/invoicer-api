import base64
import hashlib
import hmac
import os
import urllib.parse
from time import time

import jwt
import onetimepass
from flask import current_app
from passlib.hash import pbkdf2_sha256 as sha256

from .base import BaseModel, db

_DUMMY_PASSWORD_HASH = sha256.hash(base64.b64encode(os.urandom(16)).decode())


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

    organization_id = db.Column(
        db.Integer,
        db.ForeignKey("organizations.id"),
        primary_key=True,
        nullable=False,
    )
    email = db.Column(
        db.String(120), primary_key=True, nullable=False, unique=True
    )
    email_is_confirmed = db.Column(db.Boolean, nullable=False, default=False)
    email_confirmed_on = db.Column(db.DateTime, nullable=True)

    name = db.Column(db.String(64), nullable=False)
    owner = db.Column(
        db.Boolean,
        server_default=db.text("false"),
        default=False,
        nullable=False,
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

    def __init__(
        self,
        organization_id: int,
        email: str,
        name: str,
        password_plaintext: str,
        owner: bool = False,
        is_two_factor_auth: bool = True,
        two_factor_auth_type: str = "2fa_otp_email",
        otp_secret: str = "",
        otp_secret_temp: str = "",
    ):
        """Initializes a new User object, handling both required fields and defaults."""
        self.organization_id = organization_id
        self.email = email
        self.name = name
        self.password_hash = self.generate_hash(password_plaintext)
        self.owner = owner
        self.is_two_factor_auth = is_two_factor_auth
        self.two_factor_auth_type = two_factor_auth_type
        self.otp_secret = otp_secret
        self.otp_secret_temp = otp_secret_temp

    def __repr__(self):
        return f"<User {self.name}>"

    @staticmethod
    def generate_hash(password):
        return sha256.hash(password)

    @staticmethod
    def verify_hash(password, hash_):
        return sha256.verify(password, hash_)

    @staticmethod
    def check_login_password(user, password):
        """Unknown users cost the same hash as known ones, so response time
        doesn't reveal which emails have accounts."""
        ok = User.verify_hash(
            password, user.password_hash if user else _DUMMY_PASSWORD_HASH
        )
        return user is not None and ok

    def get_totp_uri(self):
        return f"otpauth://totp/invoicer-app:{urllib.parse.quote(self.email)}?secret={self.otp_secret_temp}&issuer=invoicer-app"

    @staticmethod
    def generate_otp_secret():
        return base64.b32encode(os.urandom(10)).decode("utf-8")

    def get_totp_code(self, expire_in_sec=30):
        """param expire_in_sec: length of TOTP interval (30 seconds by default)"""
        return onetimepass.get_totp(
            self.otp_secret, interval_length=expire_in_sec
        )

    def verify_totp(self, token, expire_in_sec=30):
        return onetimepass.valid_totp(
            token, self.otp_secret, interval_length=expire_in_sec
        )

    def verify_totp_temp(self, token):
        return onetimepass.valid_totp(token, self.otp_secret_temp)

    ##### Password reset ########
    @staticmethod
    def _reset_signing_key():
        """Key derived from the app secret, so a reset token can never be
        mistaken for (or forged into) an access token."""
        secret = (
            current_app.config.get("JWT_SECRET_KEY") or current_app.secret_key
        )
        return hmac.new(
            secret.encode(), b"invoicer:password-reset", hashlib.sha256
        ).digest()

    def _password_fingerprint(self):
        return hashlib.sha256(self.password_hash.encode()).hexdigest()[:32]

    def get_reset_password_token(self, expires_in=3600):
        """Bound to the current password hash: as soon as the password
        changes (including by using this very token), the token is dead."""
        return jwt.encode(
            {
                "purpose": "reset_password",
                "reset_password": self.id,
                "pwd": self._password_fingerprint(),
                "exp": time() + expires_in,
            },
            self._reset_signing_key(),
            algorithm="HS256",
        )

    @staticmethod
    def verify_reset_password_token(token):
        try:
            payload = jwt.decode(
                token,
                User._reset_signing_key(),
                algorithms=["HS256"],
                options={"require": ["exp"]},
            )
        except jwt.PyJWTError:
            return None
        if payload.get("purpose") != "reset_password":
            return None
        user = User.query.filter_by(id=payload.get("reset_password")).first()
        if user is None or not hmac.compare_digest(
            str(payload.get("pwd", "")), user._password_fingerprint()
        ):
            return None
        return user
