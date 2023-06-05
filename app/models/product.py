from app.models import db, BaseModel

class Product(BaseModel):
    __tablename__ = 'products'

    id_seq = db.Sequence(__tablename__+'_id_seq')

    id = db.Column(
        db.Integer,
        id_seq,
        server_default=id_seq.next_value(),
        autoincrement=True,
        primary_key=False,
        unique=True,
        nullable=False)

    """
    Primary keys: organization_id, name
    """

    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), primary_key=True, nullable=False)
    name = db.Column(db.String(100), primary_key=True, nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=True)
    description = db.Column(db.String(255), nullable=True)
    unit_price = db.Column(db.Numeric(10,3), server_default='0.00', default=0.00, nullable=False)
    archived = db.Column(db.Boolean, server_default=db.text('false'), default=False, nullable=False)

    account = db.relationship("Account", backref="products")