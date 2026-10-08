import base64
import hashlib
import hmac
import os
import re
import secrets
import time
import urllib.parse
from datetime import datetime, timedelta, timezone

import jwt
import onetimepass
from flask import current_app
from passlib.hash import pbkdf2_sha256 as sha256

from .backup_code import BackupCode
from .base import BaseModel, db

_DUMMY_PASSWORD_HASH = sha256.hash(base64.b64encode(os.urandom(16)).decode())

TOTP_STEP_SECONDS = 30
EMAIL_OTP_TTL = timedelta(minutes=10)
EMAIL_OTP_MAX_ATTEMPTS = 5
BACKUP_CODE_COUNT = 10
BACKUP_CODE_LENGTH = 10
# No 0/O or 1/I, so a code read off a screen or paper can't be mistyped.
_BACKUP_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _now_ts():
    """Single clock for everything time-based in this model (patched in tests)."""
    return time.time()


def _utcnow():
    return datetime.fromtimestamp(_now_ts(), timezone.utc).replace(tzinfo=None)


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
    otp_secret = db.Column(db.String(32), nullable=False)
    otp_secret_temp = db.Column(db.String(32), nullable=False)

    # Email codes: random, keyed-hashed, short-lived, single-use.
    email_otp_hash = db.Column(db.String(64), nullable=True)
    email_otp_expires_at = db.Column(db.DateTime, nullable=True)
    email_otp_attempts = db.Column(
        db.Integer, server_default="0", default=0, nullable=False
    )
    # Last accepted authenticator time step, so a code can't be replayed.
    totp_last_used_step = db.Column(db.BigInteger, nullable=True)

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

    @staticmethod
    def generate_otp_secret():
        """160 bits (32 base32 chars), the size RFC 4226 recommends."""
        return base64.b32encode(os.urandom(20)).decode("utf-8")

    @staticmethod
    def _derived_key(purpose: bytes):
        """Per-purpose key derived from the app secret, so tokens and codes
        made for one purpose can never be used for another."""
        secret = (
            current_app.config.get("JWT_SECRET_KEY") or current_app.secret_key
        )
        return hmac.new(secret.encode(), purpose, hashlib.sha256).digest()

    def _code_digest(self, kind: str, code: str):
        """Keyed hash of a short code, bound to this user and purpose."""
        return hmac.new(
            self._derived_key(b"invoicer:otp-codes"),
            f"{kind}:{self.id}:{code}".encode(),
            hashlib.sha256,
        ).hexdigest()

    ##### Email codes ########
    def issue_email_otp(self):
        """New random code; replaces (and so invalidates) any previous one."""
        code = f"{secrets.randbelow(1_000_000):06d}"
        self.email_otp_hash = self._code_digest("email-otp", code)
        self.email_otp_expires_at = _utcnow() + EMAIL_OTP_TTL
        self.email_otp_attempts = 0
        self.update()
        return code

    def _clear_email_otp(self):
        self.email_otp_hash = None
        self.email_otp_expires_at = None
        self.email_otp_attempts = 0

    def verify_email_otp(self, code):
        """Single use: a correct code is consumed, and the code is burned
        after too many wrong guesses or once it expires."""
        if not self.email_otp_hash or not self.email_otp_expires_at:
            return False
        if (
            _utcnow() > self.email_otp_expires_at
            or self.email_otp_attempts >= EMAIL_OTP_MAX_ATTEMPTS
        ):
            self._clear_email_otp()
            self.update()
            return False
        if hmac.compare_digest(
            self._code_digest("email-otp", str(code)), self.email_otp_hash
        ):
            self._clear_email_otp()
            self.update()
            return True
        self.email_otp_attempts += 1
        if self.email_otp_attempts >= EMAIL_OTP_MAX_ATTEMPTS:
            self._clear_email_otp()
        self.update()
        return False

    ##### Authenticator app (TOTP) ########
    def get_totp_uri(self):
        return f"otpauth://totp/invoicer-app:{urllib.parse.quote(self.email)}?secret={self.otp_secret_temp}&issuer=invoicer-app"

    @staticmethod
    def _matching_totp_step(secret, token):
        """Time step the token belongs to, accepting one step of clock drift
        either way; None if it matches none of them."""
        token = str(token)
        if not re.fullmatch(r"\d{6}", token):
            return None
        current = int(_now_ts() // TOTP_STEP_SECONDS)
        for step in (current, current - 1, current + 1):
            expected = f"{onetimepass.get_hotp(secret, step):06d}"
            if hmac.compare_digest(expected, token):
                return step
        return None

    def verify_totp_app(self, token):
        """Accept a code once: it must be newer than the last one used."""
        step = self._matching_totp_step(self.otp_secret, token)
        if step is None:
            return False
        if (
            self.totp_last_used_step is not None
            and step <= self.totp_last_used_step
        ):
            return False
        self.totp_last_used_step = step
        self.update()
        return True

    def verify_totp_temp(self, token):
        """Check the code typed while setting up a new authenticator. On
        success the step is recorded, so that same code can't also log in."""
        step = self._matching_totp_step(self.otp_secret_temp, token)
        if step is None:
            return False
        self.totp_last_used_step = step
        return True

    ##### Backup codes ########
    @staticmethod
    def _normalize_backup_code(raw):
        return re.sub(r"[\s-]", "", str(raw)).upper()

    @staticmethod
    def looks_like_backup_code(raw):
        return len(User._normalize_backup_code(raw)) == BACKUP_CODE_LENGTH

    def generate_backup_codes(self):
        """Replace all backup codes. Plaintext is returned once, never stored."""
        BackupCode.query.filter_by(user_id=self.id).delete()
        codes = []
        for _ in range(BACKUP_CODE_COUNT):
            raw = "".join(
                secrets.choice(_BACKUP_CODE_ALPHABET)
                for _ in range(BACKUP_CODE_LENGTH)
            )
            db.session.add(
                BackupCode(
                    user_id=self.id,
                    code_hash=self._code_digest("backup-code", raw),
                )
            )
            codes.append(f"{raw[:5]}-{raw[5:]}")
        db.session.commit()
        return codes

    def consume_backup_code(self, raw):
        """True exactly once per code (atomic, so two requests can't both win)."""
        normalized = self._normalize_backup_code(raw)
        if len(normalized) != BACKUP_CODE_LENGTH:
            return False
        row = BackupCode.query.filter_by(
            user_id=self.id,
            code_hash=self._code_digest("backup-code", normalized),
            used_at=None,
        ).first()
        if row is None:
            return False
        updated = BackupCode.query.filter_by(id=row.id, used_at=None).update(
            {"used_at": _utcnow()}
        )
        db.session.commit()
        return updated == 1

    def remaining_backup_codes(self):
        return BackupCode.query.filter_by(user_id=self.id, used_at=None).count()

    def reset_two_factor(self):
        """Back to plain email codes with a fresh secret and no backup codes."""
        self.two_factor_auth_type = "2fa_otp_email"
        self.is_two_factor_auth = True
        self.otp_secret = User.generate_otp_secret()
        self.otp_secret_temp = ""
        self.totp_last_used_step = None
        self._clear_email_otp()
        BackupCode.query.filter_by(user_id=self.id).delete()
        db.session.commit()

    ##### Password reset ########
    @staticmethod
    def _reset_signing_key():
        """Key derived from the app secret, so a reset token can never be
        mistaken for (or forged into) an access token."""
        return User._derived_key(b"invoicer:password-reset")

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
                "exp": _now_ts() + expires_in,
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
