from .base import BaseModel, db


class BackupCode(BaseModel):
    """One single-use recovery code. Only a keyed hash is stored."""

    __tablename__ = "backup_codes"
    __table_args__ = (
        db.UniqueConstraint(
            "user_id", "code_hash", name="uq_backup_codes_user_hash"
        ),
    )

    id = db.Column(
        db.Integer, autoincrement=True, primary_key=True, nullable=False
    )
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code_hash = db.Column(db.String(64), nullable=False)
    used_at = db.Column(db.DateTime, nullable=True)
