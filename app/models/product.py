from app.models import db, BaseModel

class Product(BaseModel):
    __tablename__ = 'products'

    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.String(255), nullable=True)
    unit_price = db.Column(db.Numeric(10,3), server_default='0.00', default=0.00, nullable=False)
    archived = db.Column(db.Boolean, server_default=db.text('false'), default=False, nullable=False)

    account = db.relationship("Account", backref="products")