"""The audit log: who did what to the books, and when (docs/ledger-design.md).

A row is written in the same transaction as the change it describes, by
app/audit.py, and can never be changed or deleted: a trigger refuses it.
"""

from sqlalchemy.dialects.postgresql import JSONB

from .base import db


class AuditLog(db.Model):
    __tablename__ = "audit_log"
    __table_args__ = (
        db.CheckConstraint(
            "action ~ '^[a-z_]+[.][a-z_]+$'", name="ck_audit_log_action"
        ),
        db.Index(
            "ix_audit_log_entity",
            "organization_id",
            "entity_type",
            "entity_id",
        ),
        db.Index("ix_audit_log_org_time", "organization_id", "occurred_at"),
    )

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    organization_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"), nullable=False
    )
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    occurred_at = db.Column(
        db.DateTime(timezone=True),
        server_default=db.func.now(),
        nullable=False,
    )
    # "journal_entry.posted", "fiscal_year.closed", ...: the entity, a dot and
    # what happened to it
    action = db.Column(db.String(50), nullable=False)
    entity_type = db.Column(db.String(30), nullable=False)
    entity_id = db.Column(db.Integer, nullable=False)
    details = db.Column(
        JSONB, server_default=db.text("'{}'::jsonb"), nullable=False
    )

    user = db.relationship("User", viewonly=True, lazy="joined")
