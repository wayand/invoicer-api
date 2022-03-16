from app.models import db, BaseModel

class TaxRate(BaseModel):
    __tablename__ = 'tax_rates'

    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    name = db.Column(db.String(100), unique=True, nullable=False)
    abbreviation = db.Column(db.String(10), unique=True, nullable=False)
    applies_to_purchases = db.Column(db.Boolean, server_default=db.text('false'), default=False, nullable=False)
    applies_to_sales = db.Column(db.Boolean, server_default=db.text('false'), default=False, nullable=False)
    description = db.Column(db.String(200), server_default='', default='', nullable=True)
    is_active = db.Column(db.Boolean, server_default=db.text('false'), default=False, nullable=False)
    is_predefined = db.Column(db.Boolean, server_default=db.text('false'), default=False, nullable=False)
    net_amount_meta_field_id = db.Column(db.Integer, unique=True, nullable=True)
    predefined_tag = db.Column(db.String(100), server_default='', default='', nullable=False)
    rate = db.Column(db.Numeric(), server_default='0', default=0, nullable=False)
    tax_rate_group = db.Column(db.String(100), server_default='danish', default='danish', nullable=False)

    def __repr__(self):
        return '<TaxRate {}, organization_id{}>'.format(self.id, self.organization_id)
