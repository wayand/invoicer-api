from datetime import datetime
from flask import request, current_app, jsonify, abort, session
from app.routes import bp
from app.models import (
    db,
    User,
    Organization,
    RevokedToken,
    useremail_schema,
    user_schema,
    usertoken_schema,
    userchangepassword_schema,
    usertotpsetupdelete_schema,
    usertotpsetup_schema,
    reset_password_schema,
)
from app.email import send_password_reset_email, send_confirm_mail, send_totp_code_email
from app import jwt
from io import BytesIO
import pyqrcode
from itsdangerous import URLSafeTimedSerializer

from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    jwt_required,
    current_user,
    get_jwt_identity,
    get_jwt,
)


@jwt.user_lookup_loader
def user_lookup_callback(_jwt_header, jwt_data):
    identity = jwt_data["sub"]
    return User.query.filter_by(email=identity).one_or_none()


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
@jwt_required()
def delete_totp_auth():
    try:
        json_data = request.get_json()
        if not json_data:
            return {"error": ["No Password provided"]}, 400

        errors = usertotpsetupdelete_schema.validate(json_data)
        if errors:
            return {"errors": errors}, 422

        password_hash = usertotpsetupdelete_schema.load(json_data).get("password_hash")
        user = current_user
        if User.verify_hash(password_hash, user.password_hash):
            user.otp_secret = User.generate_otp_secret()
            user.otp_secret_temp = ""
            user.is_two_factor_auth = True
            user.two_factor_auth_type = "2fa_otp_email"
            user.save()
            return {"message": "successfully totp deleted"}
        else:
            return {"errors": {"password": "Invalid password entered"}}, 422

    except Exception as e:
        return {"error": str(e)}, 500


@bp.post("/auth/totp-setup")
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
        return {"error": str(e)}, 500


def generate_token(email):
    serializer = URLSafeTimedSerializer(current_app.config["JWT_SECRET_KEY"])
    return serializer.dumps(email, salt=current_app.config["SECURITY_PASSWORD_SALT"])


def confirm_token(token, expiration=3600):
    serializer = URLSafeTimedSerializer(current_app.config["JWT_SECRET_KEY"])
    try:
        email = serializer.loads(
            token, salt=current_app.config["SECURITY_PASSWORD_SALT"], max_age=expiration
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
        return {"error": ["The confirmation link is invalid or has expired."]}, 400

@bp.post("/auth/resend-totp-email")
@jwt_required(optional=True)
def resend_totp_email():
    identity = get_jwt_identity()
    if identity:
        return {"error": ["Can't send totp for an already authenticated user!"], "ses": session.get('logging_in_user')}, 400
    else:
        user = User.find_by(email=session.get('logging_in_user'))
        if not user:
            return {"error": ["not found user"]}, 400
        send_totp_code_email(user)
        return {"message": "A new TOTP email has been sent.", "ses": session.get('logging_in_user')}

@bp.post("/auth/resend-confirmation-email")
@jwt_required()
def resend_confirmation_email():
    if current_user.email_is_confirmed:
        return {"error": ["Account email already confirmed."]}, 400
    token = generate_token(current_user.email)
    send_confirm_mail(current_user.email, token=token)
    return {"message": "A new confirmation email has been sent."}


@bp.post("/auth/reset-password")
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
            return {"error": {"resetCode": "Reset code is wrong!"}}

        user.password_hash = User.generate_hash(data.get("new_password"))
        user.update()

        return {"message": "Password Successfully reseted..."}

    except Exception as e:
        return {"error": str(e)}, 500


@bp.post("/auth/send-reset-mail")
def send_reset_mail():
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
            send_password_reset_email(user)
            return {
                "message": "Check your email for the instructions to reset your password."
            }
        else:
            return {"errors": {"email": "We Couldn't find entered email address"}}, 422

    except Exception as e:
        return {"error": str(e)}, 500


@bp.post("/auth/change-password")
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
            user.save()
            return {"message": "Password successfully changed"}, 200
        else:
            return {"error": "Old password is wrong"}, 422
    except Exception as e:
        return {"error": str(e)}, 500


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


@bp.post("/auth/token")
def get_token():
    try:
        json_data = request.get_json()
        if not json_data:
            return {"error": ["No input data provided"]}, 400
    except Exception as e:
        return {"error": str(e)}, 500

    errors = usertoken_schema.validate(json_data)
    if errors:
        return {"errors": errors}, 422

    try:
        session.pop('logging_in_user', None)
        user_data = usertoken_schema.load(json_data)
        # Searching user by username
        user = User.find_by(email=user_data["email"])
        if not user:
            return {"error": f"User by email '{user_data['email']}' not found!"}, 404
        organization = Organization.find_by(id=user.organization_id)
        if not organization:
            return {"error": "not found organization"}, 404
        if not User.verify_hash(user_data["password_hash"], user.password_hash):
            return {"error": "Wrong credentials"}, 422
        if not user.is_two_factor_auth:
            return {"error": "Wrong 2fa method"}, 422
        
        session['logging_in_user'] = user.email
        two_factor_code = user_data.get("otp_2fa")
        if two_factor_code is None:
            if not user.two_factor_auth_type == "2fa_mobile_app":
                """send the 2fa_code to email address"""
                send_totp_code_email(user)
            return {
                "message": "2fa_otp",
                "twoFactorType": user.two_factor_auth_type,
                "ses": session.get('logging_in_user')
            }, 206

        expire_in_sec = 30 if user.two_factor_auth_type == "2fa_mobile_app" else 3600
        if user.verify_totp(two_factor_code, expire_in_sec=expire_in_sec):
            session.pop('logging_in_user', None)
            access_token = create_access_token(
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
                },
            )
            refresh_token = create_refresh_token(identity=user.email)

            return {
                "accessToken": access_token,
                "refreshToken": refresh_token,
            }
        else:
            return {"error": "2FA is wrong, please try again"}, 422

    except Exception as e:
        return {"error": str(e)}, 500


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
    identity = get_jwt_identity()
    access_token = create_access_token(
        identity=identity,
        additional_claims={
            "aud": "wayand.dk",
            "name": current_user.name,
            "email": current_user.email,
            "isEmailConfirmed": current_user.email_is_confirmed,
            "isTwoFactorAuth": current_user.is_two_factor_auth,
            "twoFactorAuthType": current_user.two_factor_auth_type,
            "organizationId": current_user.organization_id,
            "organizationSlug": organization.slug,
        },
    )
    return {"accessToken": access_token}


@bp.post("/auth/revoke-access-token")
@jwt_required()
def revoke_access_token():
    jti = get_jwt()["jti"]

    try:
        revoked_token = RevokedToken(jti=jti)
        revoked_token.save()
        return {"message": "Access token has been revoked"}, 200
    except Exception as e:
        abort(500, e)


@bp.post("/auth/revoke-refresh-token")
@jwt_required(refresh=True)
def revoke_refresh_token():
    jti = get_jwt()["jti"]

    try:
        revoked_token = RevokedToken(jti=jti)
        revoked_token.save()
        return {"message": "Refresh token has been revoked"}, 200
    except Exception as e:
        abort(500, e)
