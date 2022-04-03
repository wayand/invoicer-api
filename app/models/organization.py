from app.models import db, BaseModel

class Organization(BaseModel):
    __tablename__ = 'organizations'

    id = db.Column(db.Integer, autoincrement=True, primary_key=True, nullable=False)

    """
    Primary keys: id
    """

    registration_no = db.Column(db.String(50), server_default='', default='', nullable=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)

    logo = db.Column(db.String(255), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    street = db.Column(db.String(100), nullable=True)
    zipcode = db.Column(db.String(10), nullable=True)
    city = db.Column(db.String(50), nullable=True)
    country_id = db.Column(db.Integer, db.ForeignKey('countries.id'), nullable=False)

    invoice_setting = db.relationship('InvoiceSetting', backref="organizations", uselist=False)
    country = db.relationship('Country', backref="organizations")
    users = db.relationship('User', backref="organizations", cascade="all, delete")

    def __repr__(self):
        return f'<Organization {self.id}, {self.name}>'