from enum import unique
from app.models import db, BaseModel

class TaxRate(BaseModel):
    __tablename__ = 'tax_rates'

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
    Primary keys: organization_id, name, abbreviation
    """

    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), primary_key=True, nullable=False)
    name = db.Column(db.String(100), primary_key=True, nullable=False)
    abbreviation = db.Column(db.String(10), primary_key=True, nullable=False)

    applies_to_purchases = db.Column(db.Boolean, server_default=db.text('false'), default=False, nullable=False)
    applies_to_sales = db.Column(db.Boolean, server_default=db.text('false'), default=False, nullable=False)
    description = db.Column(db.String(200), server_default='', default='', nullable=True)
    is_active = db.Column(db.Boolean, server_default=db.text('false'), default=False, nullable=False)
    is_predefined = db.Column(db.Boolean, server_default=db.text('false'), default=False, nullable=False)
    net_amount_meta_field_id = db.Column(db.Integer, nullable=True)
    predefined_tag = db.Column(db.String(100), server_default='', default='', nullable=False)
    rate = db.Column(db.Numeric(), server_default='0', default=0, nullable=False)
    tax_rate_group = db.Column(db.String(100), server_default='danish', default='danish', nullable=False)

    def __repr__(self):
        return '<TaxRate {}, organization_id{}>'.format(self.id, self.organization_id)
