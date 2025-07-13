from app.models import db, BaseModel

class InvoiceSetting(BaseModel):
    __tablename__ = 'invoice_settings'

    id = db.Column(db.Integer, autoincrement=True, primary_key=True, nullable=False)

    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), unique=True, nullable=False)
    default_account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=False)
    default_deposit_account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=False)

    template_id = db.Column(db.String(100), server_default='1', default='1', nullable=False)
    hide_product_numbers = db.Column(db.Boolean, server_default=db.text('false'), default=False, nullable=False)
    lines_incl_vat = db.Column(db.Boolean, server_default=db.text('false'), default=False, nullable=False)

    invoice_no_mode = db.Column(db.String(10), server_default='manual', default='manual', nullable=False)
    next_invoice_no = db.Column(db.Integer, server_default='0', default=0, nullable=False)
    default_reminder_fee = db.Column(db.Numeric(), server_default='0', default=0, nullable=False)

    def __repr__(self):
        return '<InvoiceSetting {}, organization_id{}>'.format(self.id, self.organization_id)