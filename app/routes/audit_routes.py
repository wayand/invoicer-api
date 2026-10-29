from flask import request
from flask_jwt_extended import current_user, jwt_required

from app.models.audit import AuditLog
from app.models.audit_schema import audit_log_schema
from app.routes import bp

DEFAULT_LIMIT, MAX_LIMIT = 50, 200


@bp.get("/audit-log")
@jwt_required()
def get_audit_log():
    """What was done to the books, newest first. Filter with entity_type and
    entity_id (for one entry, year or account), or action."""
    query = AuditLog.query.filter_by(
        organization_id=current_user.organization_id
    )
    for key in ("entity_type", "action"):
        value = request.args.get(key)
        if value:
            query = query.filter(getattr(AuditLog, key) == value)
    entity_id = request.args.get("entity_id", type=int)
    if entity_id is not None:
        query = query.filter(AuditLog.entity_id == entity_id)
    limit = min(request.args.get("limit", DEFAULT_LIMIT, type=int), MAX_LIMIT)
    offset = max(request.args.get("offset", 0, type=int), 0)
    rows = (
        query.order_by(AuditLog.id.desc())
        .limit(max(limit, 1))
        .offset(offset)
        .all()
    )
    return audit_log_schema.dump(rows)
