from app.models import db, BaseModel

class Country(BaseModel):
    __tablename__ = 'countries'

    currency_id = db.Column(db.String(10), nullable=False)
    locale_id = db.Column(db.String(11), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    icon = db.Column(db.String(10), nullable=False)