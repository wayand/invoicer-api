from datetime import datetime
from io import BytesIO

import pyqrcode
from flasgger.utils import swag_from
from flask import abort, current_app, jsonify, request, session
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    current_user,
    decode_token,
    get_jwt,
    get_jwt_identity,
    jwt_required,
)
from flask_limiter.util import get_remote_address
from itsdangerous import URLSafeTimedSerializer
from jwt import PyJWTError

from app import jwt, limiter
from app.email import (
    queue_backup_code_used_email,
    queue_password_reset_email,
    send_confirm_mail,
    send_totp_code_email,
)
from app.models.base import db
from app.models.organization import Organization
from app.models.revoked_token import RevokedToken
from app.models.user import User
from app.models.user_schema import (
    reset_password_schema,
    user_schema,
    userchangepassword_schema,
    useremail_schema,
    userpassword_schema,
    usertoken_schema,
    usertotpsetup_schema,
    usertotpsetupdelete_schema,
)
from app.ratelimit import (
    email_key,
    login_in_progress_key,
    not_ok,
    user_key,
)

from . import bp

# Password-checking endpoints for logged-in users share one bucket, so a
# stolen access token can't be used as an unlimited password-guessing oracle.
password_reauth_limit = limiter.limit(
    "5 per 15 minutes",
    key_func=user_key,
    deduct_when=not_ok,
    scope="password-reauth",
)


def _server_error(error):
    current_app.logger.exception("unhandled error in auth route: %s", error)
    return {"error": "Something went wrong. Please try again."}, 500


@jwt.user_lookup_loader
def user_lookup_callback(_jwt_header, jwt_data):
    """The token's user, unless the user's sessions were ended since it was
    issued. Tokens from before token_version existed count as version 0."""
    user = User.query.filter_by(email=jwt_data["sub"]).one_or_none()
    if user is None or jwt_data.get("tv", 0) != user.token_version:
        return None
    return user


def _access_token(user, organization):
    return create_access_token(
        identity=user.email,
        additional_claims={
            "aud": "wayand.dk",
            "name": user.name,
            "email": user.email,
            "isEmailConfirmed": user.email_is_confirmed,
            "isTwoFactorAuth": user.is_two_factor_auth,
            "twoFactorAuthType": user.two_factor_auth_type,
            "organizationId": user.organization_id,
            "organizationSlug": organization.slug,
            "tv": user.token_version,
        },
    )


def _refresh_token(user):
    return create_refresh_token(
        identity=user.email, additional_claims={"tv": user.token_version}
    )


# Checking that token is in blacklist or not
@jwt.token_in_blocklist_loader
def check_if_token_is_revoked(jwt_header, jwt_payload):
    jti = jwt_payload["jti"]
    return RevokedToken.is_jti_blacklisted(jti)


@bp.get("/auth/qrcode")
@jwt_required()
def qrcode():
    user = current_user  # User.query.filter_by(email='lawangjan@hotmail.com').one_or_none()
    user.otp_secret_temp = User.generate_otp_secret()
    user.save()
    # render qrcode for FreeTOTP
    url = pyqrcode.create(user.get_totp_uri())
    stream = BytesIO()
    url.svg(stream, scale=5)
    return (
        stream.getvalue(),
        200,
        {
            "Content-Type": "image/svg+xml",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@bp.delete("/auth/totp-setup")
@password_reauth_limit
@jwt_required()
def delete_totp_auth():
    try:
        json_data = request.get_json()
        if not json_data:
            return {"error": ["No Password provided"]}, 400

        errors = usertotpsetupdelete_schema.validate(json_data)
        if errors:
            return {"errors": errors}, 422

        password_hash = usertotpsetupdelete_schema.load(json_data).get(
            "password_hash"
        )
        user = current_user
        if User.verify_hash(password_hash, user.password_hash):
            user.otp_secret = User.generate_otp_secret()
            user.otp_secret_temp = ""
            user.is_two_factor_auth = True
            user.two_factor_auth_type = "2fa_otp_email"
            user.totp_last_used_step = None
            user.save()
            return {"message": "successfully totp deleted"}
        else:
            return {"errors": {"password": "Invalid password entered"}}, 422

    except Exception as e:
        return _server_error(e)


@bp.post("/auth/totp-setup")
@password_reauth_limit
@jwt_required()
def totp_setup():
    try:
        json_data = request.get_json()
        if not json_data:
            return {"error": ["No input data provided"]}, 400

        errors = usertotpsetup_schema.validate(json_data)
        if errors:
            return {"errors": errors}, 422

        user_data = usertotpsetup_schema.load(json_data)
        password_hash = user_data.get("password_hash")
        totp_code = user_data.get("totp_code")
        user = current_user
        if User.verify_hash(password_hash, user.password_hash):
            if user.verify_totp_temp(totp_code):
                user.otp_secret = user.otp_secret_temp
                user.is_two_factor_auth = True
                user.two_factor_auth_type = "2fa_mobile_app"
                user.otp_secret_temp = ""
                user.save()
                return {"message": "successfully totp setup"}
            else:
                return {"errors": {"totp_code": "OTP code is wrong"}}, 422
        else:
            return {"errors": {"password": "Invalid password entered"}}, 422

    except Exception as e:
        return _server_error(e)


def generate_token(email):
    serializer = URLSafeTimedSerializer(current_app.config["JWT_SECRET_KEY"])
    return serializer.dumps(
        email, salt=current_app.config["SECURITY_PASSWORD_SALT"]
    )


def confirm_token(token, expiration=3600):
    serializer = URLSafeTimedSerializer(current_app.config["JWT_SECRET_KEY"])
    try:
        email = serializer.loads(
            token,
            salt=current_app.config["SECURITY_PASSWORD_SALT"],
            max_age=expiration,
        )
        return email
    except Exception:
        return False


@bp.get("/auth/is-email-confirmed")
@jwt_required()
def is_email_confirmed():
    if current_user.email_is_confirmed:
        return {"message": "Already confirmed."}
    return {"error": "Not confirmed yet."}, 401


@bp.post("/auth/confirm-email/<token>")
@jwt_required()
def confirm_email(token):
    if current_user.email_is_confirmed:
        return {"error": ["Account email already confirmed."]}, 400
    email = confirm_token(token)
    user = User.query.filter_by(email=current_user.email).first_or_404()
    if user.email == email:
        user.email_is_confirmed = True
        user.email_confirmed_on = datetime.now()
        user.update()
        return {"message": "You have confirmed your account. Thanks!"}
    else:
        return {
            "error": ["The confirmation link is invalid or has expired."]
        }, 400


@bp.post("/auth/resend-totp-email")
@limiter.limit(
    "5 per hour", key_func=login_in_progress_key, scope="resend-totp-email"
)
@limiter.limit(
    "30 per hour", key_func=get_remote_address, scope="resend-totp-email-ip"
)
@jwt_required(optional=True)
def resend_totp_email():
    identity = get_jwt_identity()
    if identity:
        return {
            "error": ["Can't send totp for an already authenticated user!"],
        }, 400
    else:
        user = User.find_by(email=session.get("logging_in_user"))
        if not user:
            return {"error": ["not found user"]}, 400
        send_totp_code_email(user)
        return {"message": "A new TOTP email has been sent."}


@bp.post("/auth/resend-confirmation-email")
@jwt_required()
def resend_confirmation_email():
    if current_user.email_is_confirmed:
        return {"error": ["Account email already confirmed."]}, 400
    token = generate_token(current_user.email)
    send_confirm_mail(current_user.email, token=token)
    return {"message": "A new confirmation email has been sent."}


@swag_from("../../swags/auth/reset_password.yaml")
@bp.post("/auth/reset-password")
@limiter.limit(
    "10 per 15 minutes",
    key_func=get_remote_address,
    deduct_when=not_ok,
    scope="reset-password",
)
def reset_password():
    try:
        json_data = request.get_json()
        if not json_data:
            return {"error": ["No input data provided"]}, 400

        errors = reset_password_schema.validate(json_data)
        if errors:
            return {"errors": errors}, 422

        data = reset_password_schema.load(json_data)
        user = User.verify_reset_password_token(data.get("reset_code"))
        if not user:
            return {
                "errors": {"resetCode": "Reset code is invalid or has expired."}
            }, 400

        user.password_hash = User.generate_hash(data.get("new_password"))
        user.token_version += 1
        user.update()

        return {"message": "Password Successfully reseted..."}

    except Exception as e:
        return _server_error(e)


@bp.post("/auth/send-reset-mail")
@limiter.limit("3 per hour", key_func=email_key, scope="send-reset-mail")
@limiter.limit(
    "20 per hour", key_func=get_remote_address, scope="send-reset-mail-ip"
)
def send_reset_mail():
    """
    Send Reset Email
    ---
    description: Send Reset Email
    """
    try:
        json_data = request.get_json()
        if not json_data:
            return {"error": ["No input data provided"]}, 400

        errors = useremail_schema.validate(json_data)
        if errors:
            return {"errors": errors}, 422

        email = useremail_schema.load(json_data).get("email")
        user = User.find_by(email=email)
        if user:
            queue_password_reset_email(user)
        # Same answer whether or not the account exists.
        return {
            "message": "If an account exists for that email address, we have sent instructions to reset the password."
        }

    except Exception as e:
        return _server_error(e)


@bp.post("/auth/change-password")
@password_reauth_limit
@jwt_required()
def change_password():
    try:
        json_data = request.get_json()
        if not json_data:
            return {"error": ["No input data provided"]}, 400

        errors = userchangepassword_schema.validate(json_data)
        if errors:
            return {"errors": errors}, 422

        user_data = userchangepassword_schema.load(json_data)
        user = current_user
        old_password = user_data.get("password_hash")
        new_password = user_data.get("new_password")
        if User.verify_hash(old_password, user.password_hash):
            user.password_hash = User.generate_hash(new_password)
            # Ends every session, this one included; the caller gets a new one.
            user.token_version += 1
            user.save()
            organization = Organization.find_by(id=user.organization_id)
            return {
                "message": "Password successfully changed",
                "accessToken": _access_token(user, organization),
                "refreshToken": _refresh_token(user),
            }, 200
        else:
            return {"error": "Old password is wrong"}, 422
    except Exception as e:
        return _server_error(e)


@bp.get("/is-authorized")
@jwt_required()
def is_authorized():
    return jsonify(status="Authorized")


@bp.get("/auth/user")
@jwt_required()
def auth_user():
    user_email = get_jwt_identity()
    user = User.find_by(email=user_email)
    return user_schema.jsonify(user)


def _second_factor_ok(user, code):
    """The code typed at login: a backup code (10 characters) or the code for
    the account's own method (6 digits)."""
    code = str(code).strip()
    if User.looks_like_backup_code(code):
        if not user.consume_backup_code(code):
            return False
        queue_backup_code_used_email(user)
        return True
    if user.two_factor_auth_type == "2fa_mobile_app":
        return user.verify_totp_app(code)
    return user.verify_email_otp(code)


@bp.get("/auth/backup-codes")
@jwt_required()
def backup_codes_status():
    return {"remaining": current_user.remaining_backup_codes()}


@bp.post("/auth/backup-codes")
@password_reauth_limit
@jwt_required()
def regenerate_backup_codes():
    """Replace all backup codes. The plaintext is shown here, once."""
    try:
        json_data = request.get_json(silent=True)
        if not json_data:
            return {"error": ["No password provided"]}, 400

        errors = userpassword_schema.validate(json_data)
        if errors:
            return {"errors": errors}, 422

        password = userpassword_schema.load(json_data).get("password_hash")
        if not User.verify_hash(password, current_user.password_hash):
            return {"errors": {"password": "Invalid password entered"}}, 422

        codes = current_user.generate_backup_codes()
        return (
            {"codes": codes},
            200,
            {"Cache-Control": "no-store", "Pragma": "no-cache"},
        )
    except Exception as e:
        return _server_error(e)


@bp.post("/auth/token")
@limiter.limit(
    "10 per 15 minutes",
    key_func=email_key,
    deduct_when=not_ok,
    scope="login-account",
)
@limiter.limit(
    "60 per 15 minutes",
    key_func=get_remote_address,
    deduct_when=not_ok,
    scope="login-ip",
)
def get_token():
    """
    Get Auth Token
    ---
    description: Get Auth Token
    """
    json_data = request.get_json(silent=True)
    if not json_data:
        return {"error": ["No input data provided"]}, 400

    errors = usertoken_schema.validate(json_data)
    if errors:
        return {"errors": errors}, 422

    try:
        session.pop("logging_in_user", None)
        user_data = usertoken_schema.load(json_data)
        user = User.find_by(email=user_data["email"])
        # Unknown email and wrong password must be indistinguishable.
        if not User.check_login_password(user, user_data["password_hash"]):
            return {"error": "Wrong credentials"}, 422
        organization = Organization.find_by(id=user.organization_id)
        if not organization:
            return {"error": "Wrong credentials"}, 422
        if not user.is_two_factor_auth:
            return {"error": "Wrong 2fa method"}, 422

        session["logging_in_user"] = user.email
        two_factor_code = user_data.get("otp_2fa")
        if two_factor_code is None:
            if not user.two_factor_auth_type == "2fa_mobile_app":
                """send the 2fa_code to email address"""
                send_totp_code_email(user)
            return {
                "message": "2fa_otp",
                "twoFactorType": user.two_factor_auth_type,
            }, 206

        if _second_factor_ok(user, two_factor_code):
            session.pop("logging_in_user", None)
            access_token = _access_token(user, organization)
            refresh_token = _refresh_token(user)

            return {
                "accessToken": access_token,
                "refreshToken": refresh_token,
            }
        else:
            return {"error": "2FA is wrong, please try again:"}, 422

    except Exception as e:
        return _server_error(e)


# We are using the `refresh=True` options in jwt_required to only allow
# refresh tokens to access this route.
@bp.post("/auth/refresh-token")
@jwt_required(refresh=True)
def refresh_token():
    """
    Refresh the access token using refresh token.
    If we are refreshing a token here we have not verified the users password in
    a while, so mark the newly created access token as not fresh
    """
    organization = Organization.find_by(id=current_user.organization_id)
    if organization is None:
        raise ValueError("Organization not found")

    access_token = _access_token(current_user, organization)
    return {"accessToken": access_token}


@bp.post("/auth/revoke-access-token")
@jwt_required()
def revoke_access_token():
    try:
        RevokedToken.revoke(get_jwt())
        return {"message": "Access token has been revoked"}, 200
    except Exception as e:
        abort(500, e)


@bp.post("/auth/revoke-refresh-token")
@jwt_required(refresh=True)
def revoke_refresh_token():
    try:
        RevokedToken.revoke(get_jwt())
        return {"message": "Refresh token has been revoked"}, 200
    except Exception as e:
        abort(500, e)


@bp.post("/auth/logout")
@jwt_required()
def logout():
    """Ends this session: revokes the access token that made the request and
    the refresh token sent along with it, if any."""
    json_data = request.get_json(silent=True)
    refresh_token = (
        json_data.get("refresh_token") if isinstance(json_data, dict) else None
    )
    refresh_claims = None
    if refresh_token is not None:
        refresh_claims = _own_refresh_claims(refresh_token)
        if refresh_claims is None:
            return {"error": "Invalid refresh token"}, 400

    try:
        RevokedToken.revoke(get_jwt(), commit=False)
        if refresh_claims is not None:
            RevokedToken.revoke(refresh_claims, commit=False)
        RevokedToken.purge_expired(commit=False)
        db.session.commit()
        return {"message": "Logged out"}, 200
    except Exception as e:
        db.session.rollback()
        return _server_error(e)


def _own_refresh_claims(token):
    """The claims of a valid refresh token that belongs to the current user,
    otherwise None."""
    if not isinstance(token, str):
        return None
    try:
        claims = decode_token(token)
    except PyJWTError:
        return None
    if claims.get("type") != "refresh" or claims["sub"] != current_user.email:
        return None
    return claims
