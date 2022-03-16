from flask import request, current_app, jsonify, abort
from app.routes import bp
from app.models import (
    db, User, Organization, 
    RevokedToken,
    useremail_schema,
    user_schema,
    usertoken_schema, 
    userchangepassword_schema, 
    usertotpsetupdelete_schema, 
    usertotpsetup_schema,
    reset_password_schema)
from app.email import send_password_reset_email
from app import jwt
from io import BytesIO
import pyqrcode

from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    jwt_required,
    current_user,
    get_jwt_identity,
    get_jwt
)

@jwt.user_lookup_loader
def user_lookup_callback(_jwt_header, jwt_data):
    identity = jwt_data["sub"]
    return User.query.filter_by(email=identity).one_or_none()

# Checking that token is in blacklist or not
@jwt.token_in_blocklist_loader
def check_if_token_is_revoked(jwt_header, jwt_payload):
    jti = jwt_payload['jti']
    return RevokedToken.is_jti_blacklisted(jti)

@bp.get('/auth/qrcode')
@jwt_required()
def qrcode():
    user = current_user # User.query.filter_by(email='lawangjan@hotmail.com').one_or_none()
    user.otp_secret_temp = User.generate_otp_secret()
    user.save()
    # render qrcode for FreeTOTP
    url = pyqrcode.create(user.get_totp_uri())
    stream = BytesIO()
    url.svg(stream, scale=5)
    return stream.getvalue(), 200, {
        'Content-Type': 'image/svg+xml',
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0'}

@bp.delete('/auth/totp-setup')
@jwt_required()
def delete_totp_auth():
    try:
        json_data = request.get_json()
        if not json_data:
            return {"error": ["No Password provided"]}, 400

        errors = usertotpsetupdelete_schema.validate(json_data)
        if errors:
            return {
                "errors": errors
            }, 422

        password_hash = usertotpsetupdelete_schema.load(json_data).get('password_hash')
        user = current_user
        if User.verify_hash(password_hash, user.password_hash):
            user.otp_secret = ''
            user.otp_secret_temp = ''
            user.is_two_factor_auth = False
            user.save()
            return { 'message': 'successfully totp deleted' }
        else:
            return {'errors': {'password': 'Invalid password entered'}}, 422

    except Exception as e:
        return {"error": str(e)}, 500

@bp.post('/auth/totp-setup')
@jwt_required()
def totp_setup():
    try:
        json_data = request.get_json()
        if not json_data:
            return {"error": ["No input data provided"]}, 400

        errors = usertotpsetup_schema.validate(json_data)
        if errors:
            return {
                "errors": errors
            }, 422

        user_data = usertotpsetup_schema.load(json_data)
        password_hash = user_data.get('password_hash')
        totp_code = user_data.get('totp_code')
        user = current_user
        if User.verify_hash(password_hash, user.password_hash):
            if user.verify_totp_temp(totp_code):
                user.otp_secret = user.otp_secret_temp
                user.is_two_factor_auth = True
                user.otp_secret_temp = ''
                user.save()
                return { 'message': 'successfully totp setup' }
            else:
                return { 'errors': {'totp_code': 'OTP code is wrong'} }, 422
        else:
            return {'errors': {'password': 'Invalid password entered'}}, 422

    except Exception as e:
        return {"error": str(e)}, 500

@bp.post('/auth/reset-password')
def reset_password():
    try:
        json_data = request.get_json()
        if not json_data:
            return {"error": ["No input data provided"]}, 400

        errors = reset_password_schema.validate(json_data)
        if errors:
            return {
                "errors": errors
            }, 422

        data = reset_password_schema.load(json_data)
        user = User.verify_reset_password_token(data.get('reset_code'))
        if not user:
            return { 'error': {'resetCode': 'Reset code is wrong!'} }

        user.password_hash = User.generate_hash(data.get('new_password'))
        user.update()

        return {
            'message': 'Password Successfully reseted...'
        }

    except Exception as e:
        return { 'error': str(e) }, 500

@bp.post('/auth/send-reset-mail')
def send_reset_mail():
    try:
        json_data = request.get_json()
        if not json_data:
            return {"error": ["No input data provided"]}, 400

        errors = useremail_schema.validate(json_data)
        if errors:
            return {
                "errors": errors
            }, 422
        
        email = useremail_schema.load(json_data).get('email')
        user = User.find_by(email=email)
        if user:
            send_password_reset_email(user)
            return {
                'message': 'Check your email for the instructions to reset your password.'
            }
        else:
            return {
                'errors': { 'email': 'We Couldn\'t find entered email address' }
            }, 422

    except Exception as e:
        return { 'error': str(e) }, 500

@bp.post('/auth/change-password')
@jwt_required()
def change_password():
    try:
        json_data = request.get_json()
        if not json_data:
            return {"error": ["No input data provided"]}, 400
        
        errors = userchangepassword_schema.validate(json_data)
        if errors:
            return {
                "errors": errors
            }, 422

        user_data = userchangepassword_schema.load(json_data)
        user = current_user
        old_password = user_data.get('password_hash')
        new_password = user_data.get('new_password')
        if User.verify_hash(old_password, user.password_hash):
            user.password_hash = User.generate_hash(new_password)
            user.save()
            return { 'message': 'Password successfully changed' }, 200
        else:
            return { 'error': 'Old password is wrong' }, 422
    except Exception as e:
        return { 'error': str(e) }, 500


@bp.get('/is-authorized')
@jwt_required()
def is_authorized():
    return jsonify(status="Authorized")

@bp.get('/auth/user')
@jwt_required()
def auth_user():
    return user_schema.jsonify(current_user)

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
        return {
            "errors": errors
        }, 422
    
    try:
        user_data = usertoken_schema.load(json_data)
        # Searching user by username
        user = User.find_by(email=user_data['email'])
        if not user:
            raise Exception(f"User by email '{user_data['email']}' not found!")
        organization = Organization.find_by(id=user.organization_id)
        if not user:
            return {'error': f'User email {user_data["email"]} dosn\'t exists'}, 404
        
        if User.verify_hash(user_data['password_hash'], user.password_hash):
            if not user.is_two_factor_auth:
                access_token = create_access_token(identity=user.email, 
                    additional_claims={
                        'aud': 'wayand.dk',
                        'name': user.name,
                        'email': user.email,
                        'isTwoFactorAuth': user.is_two_factor_auth,
                        "organizationId": user.organization_id,
                        'organizationSlug': organization.slug
                })
                refresh_token = create_refresh_token(identity=user.email)

                return {
                    'accessToken': access_token,
                    'refreshToken': refresh_token
                }
            else:
                if user_data.get('otp_2fa'):
                    if user.verify_totp(user_data.get('otp_2fa')):
                        access_token = create_access_token(identity=user.email, 
                            additional_claims={
                                'aud': 'wayand.dk',
                                'name': user.name,
                                'email': user.email,
                                'isTwoFactorAuth': user.is_two_factor_auth,
                                "organizationId": user.organization_id,
                                'organizationSlug': organization.slug
                        })
                        refresh_token = create_refresh_token(identity=user.email)

                        return {
                            'accessToken': access_token,
                            'refreshToken': refresh_token
                        }
                    else:
                        return {
                            'error': '2FA is wrong, please try again'
                        }, 422
                else:
                    return { 'message': '2fa_otp' }, 206
        else:
            return {'error': "Wrong credentials"}, 422

    except Exception as e:
        return {'error': str(e)}, 500


# We are using the `refresh=True` options in jwt_required to only allow
# refresh tokens to access this route.
@bp.post('/auth/refresh-token')
@jwt_required(refresh=True)
def refresh_token():
    """
    Refresh the access token using refresh token.
    If we are refreshing a token here we have not verified the users password in
    a while, so mark the newly created access token as not fresh
    """
    organization = Organization.find_by(id=current_user.organization_id)
    identity = get_jwt_identity()
    access_token = create_access_token(identity=identity, 
        additional_claims={
            'aud': 'wayand.dk',
            'name': current_user.name,
            'email': current_user.email,
            'isTwoFactorAuth': current_user.is_two_factor_auth,
            "organizationId": current_user.organization_id,
            'organizationSlug': organization.slug
    })
    return {'accessToken': access_token}

@bp.post('/auth/revoke-access-token')
@jwt_required()
def revoke_access_token():
    jti = get_jwt()['jti']

    try:
        revoked_token = RevokedToken(jti=jti)
        revoked_token.save()
        return {'message': 'Access token has been revoked'}, 200
    except Exception as e:
        abort(500, e)

@bp.post('/auth/revoke-refresh-token')
@jwt_required(refresh=True)
def revoke_refresh_token():
    jti = get_jwt()['jti']

    try:
        revoked_token = RevokedToken(jti=jti)
        revoked_token.save()
        return {'message': 'Refresh token has been revoked'}, 200
    except Exception as e:
        abort(500, e)