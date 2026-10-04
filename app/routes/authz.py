from functools import wraps

from flask import abort
from flask_jwt_extended import current_user


def org_member_required(fn):
    """
    Reject requests whose URL <organization_id> is not the caller's own
    organization. Must sit below @jwt_required() so current_user is loaded.

    Answers 404 rather than 403 so another tenant's ids can't be probed.
    """

    @wraps(fn)
    def wrapper(*args, **kwargs):
        if kwargs.get("organization_id") != current_user.organization_id:
            abort(404, description="Organization not found")
        return fn(*args, **kwargs)

    return wrapper
