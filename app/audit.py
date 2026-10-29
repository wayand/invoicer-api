"""Writing the audit log.

`record` adds a row to the session and flushes it: it is committed, or rolled
back, together with the change it describes. Call it in the same transaction
as the change, never after the commit.
"""

from datetime import date, datetime
from decimal import Decimal

from app.models.audit import AuditLog
from app.models.base import db


def _plain(value):
    """The details as JSON: dates as text, amounts as text with their
    decimals (a float would lose the precision the books are kept with)."""
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def record(
    organization_id: int,
    user_id: int,
    action: str,
    entity_type: str,
    entity_id: int,
    details: dict | None = None,
) -> AuditLog:
    row = AuditLog(
        organization_id=organization_id,
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=_plain(details or {}),
    )
    db.session.add(row)
    db.session.flush()
    return row
