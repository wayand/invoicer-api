from app.models import db, BaseModel

class Client(BaseModel):
    __tablename__ = 'clients'

    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    registration_no = db.Column(db.String(50), nullable=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    logo = db.Column(db.String(255), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    street = db.Column(db.String(100), nullable=True)
    zipcode = db.Column(db.String(10), nullable=True)
    city = db.Column(db.String(50), nullable=True)
    archived = db.Column(db.Boolean, server_default=db.text('false'), default=False, nullable=False)
    country_id = db.Column(db.Integer, db.ForeignKey('countries.id'), nullable=False)
    contactperson_name = db.Column(db.String(255), nullable=True)
    contactperson_email = db.Column(db.String(255), nullable=True)
    type = db.Column(db.String(10), server_default='company', default='company', nullable=False)