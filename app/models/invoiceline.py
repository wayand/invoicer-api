from app.models.base import BaseModel
from app.models import db, BaseModel, invoice

class InvoiceLine(BaseModel):
    __tablename__ = 'invoice_lines'

    invoice_id = db.Column(db.Integer, db.ForeignKey('invoices.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    quantity = db.Column(db.Numeric(10,3), server_default='0.00', default=0.00, nullable=False)
    unit_price = db.Column(db.Numeric(10,3), server_default='0.00', default=0.00, nullable=False)
    amount = db.Column(db.Numeric(10,3), server_default='0.00', default=0.00, nullable=False)

    def __repr__(self):
        return '<InvoiceLine {}>'.format(self.description)