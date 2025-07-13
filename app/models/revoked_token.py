from app.models import db, BaseModel

class RevokedToken(BaseModel):
    __tablename__ = 'revoked_tokens'

    id = db.Column(db.Integer, primary_key=True)
    jti = db.Column(db.String(120))

    """
    Checking that token is blacklisted
    """
    @classmethod
    def is_jti_blacklisted(cls, jti):
        token = cls.query.filter_by(jti=jti).scalar()
        return token is not None