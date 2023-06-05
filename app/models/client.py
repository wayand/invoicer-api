from app.models import db, BaseModel

class Client(BaseModel):
    __tablename__ = 'clients'

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
    Primary keys: organization_id, name, registration_no
    """

    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), primary_key=True, nullable=False)
    name = db.Column(db.String(100), primary_key=True, nullable=False)
    registration_no = db.Column(db.String(50), server_default='', default='', primary_key=True, nullable=True)

    email = db.Column(db.String(255), nullable=False)
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