from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from .base import BaseModel


class RevokedToken(BaseModel):
    __tablename__ = "revoked_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    jti: Mapped[str] = mapped_column(String(120))

    """
    Checking that token is blacklisted
    """

    @classmethod
    def is_jti_blacklisted(cls, jti):
        token = cls.query.filter_by(jti=jti).scalar()
        return token is not None
