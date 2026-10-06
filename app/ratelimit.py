from flask import request, session
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from flask_limiter.util import get_remote_address


def _body_email():
    data = request.get_json(silent=True)
    email = data.get("email") if isinstance(data, dict) else None
    return email.strip().lower() if isinstance(email, str) else None


def email_key():
    """Per target account, whether or not the account exists."""
    return f"email:{_body_email() or get_remote_address()}"


def login_in_progress_key():
    return f"login:{session.get('logging_in_user') or get_remote_address()}"


def user_key():
    """Per authenticated user. Runs before the route's own @jwt_required."""
    try:
        verify_jwt_in_request(optional=True)
        identity = get_jwt_identity()
    except Exception:
        identity = None
    return f"user:{identity or get_remote_address()}"


def not_ok(response):
    """Only count attempts that did not fully succeed."""
    return response.status_code != 200
