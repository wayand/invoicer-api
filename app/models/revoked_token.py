from datetime import UTC, datetime

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Mapped, mapped_column

from .base import BaseModel, db


def utc_now():
    """Naive UTC, as stored in revoked_tokens.expires_at."""
    return datetime.now(UTC).replace(tzinfo=None)


class RevokedToken(BaseModel):
    __tablename__ = "revoked_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    jti: Mapped[str] = mapped_column(String(120), unique=True)
    # When the token would have expired anyway, after which the row is useless.
    expires_at: Mapped[datetime] = mapped_column(DateTime)

    """
    Checking that token is blacklisted
    """

    @classmethod
    def is_jti_blacklisted(cls, jti):
        token = cls.query.filter_by(jti=jti).scalar()
        return token is not None

    @classmethod
    def revoke(cls, token_claims, commit=True):
        """Blocklist a token given its decoded claims. Revoking a token twice
        is fine."""
        expires_at = datetime.fromtimestamp(token_claims["exp"], UTC).replace(
            tzinfo=None
        )
        db.session.execute(
            insert(cls)
            .values(
                jti=token_claims["jti"],
                expires_at=expires_at,
            )
            .on_conflict_do_nothing(index_elements=["jti"])
        )
        if commit:
            db.session.commit()

    @classmethod
    def purge_expired(cls, commit=True):
        """Drop rows for tokens that have expired by themselves."""
        cls.query.filter(cls.expires_at < utc_now()).delete(
            synchronize_session=False
        )
        if commit:
            db.session.commit()
