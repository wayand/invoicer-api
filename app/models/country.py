from .base import BaseModel, db


class Country(BaseModel):
    __tablename__ = "countries"

    id = db.Column(
        db.Integer, autoincrement=True, primary_key=True, nullable=False
    )

    currency_id = db.Column(db.String(10), nullable=False)
    locale_id = db.Column(db.String(11), nullable=False)
    name = db.Column(db.String(100), unique=True, nullable=False)
    icon = db.Column(db.String(10), nullable=False)
