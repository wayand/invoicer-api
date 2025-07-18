from enum import unique
from app.models import db, BaseModel

class AccountType(BaseModel):
    __tablename__ = 'account_types'

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

    normal_balance = db.Column(db.String(100), nullable=False)
    report_type = db.Column(db.String(100), nullable=False)

class AccountGroup(BaseModel):
    __tablename__ = 'account_groups'

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
    primary keys: organization_id, name, number
    """

    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), primary_key=True, nullable=False)
    account_type_id = db.Column(db.Integer, db.ForeignKey('account_types.id'), nullable=False)
    name = db.Column(db.String(100), primary_key=True, nullable=False)
    number = db.Column(db.Integer, primary_key=True, nullable=False)
    interval_start = db.Column(db.Integer, nullable=False)
    interval_end = db.Column(db.Integer, nullable=False)


class Account(BaseModel):
    __tablename__ = 'accounts'

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
    primary keys: organization_id, name, number
    """

    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), primary_key=True, nullable=False)
    account_type_id = db.Column(db.Integer, db.ForeignKey('account_types.id'), nullable=False)
    account_group_id = db.Column(db.Integer, db.ForeignKey('account_groups.id'), nullable=False)
    tax_rate_id = db.Column(db.Integer, db.ForeignKey('tax_rates.id'), nullable=True)

    account_type = db.relationship("AccountType", backref="accounts")
    account_group = db.relationship("AccountGroup", backref="accounts")
    tax_rate = db.relationship("TaxRate", backref="accounts")

    name = db.Column(db.String(100), primary_key=True, nullable=False)
    description = db.Column(db.String(100), server_default='', default='', nullable=True)
    number = db.Column(db.Integer, primary_key=True, nullable=False)
    currency_id = db.Column(db.String(10), server_default='DKK', default='DKK', nullable=False)

    bank_id= db.Column(db.Integer, nullable=True)
    bank_registration_number = db.Column(db.Integer, nullable=True)
    bank_account_number = db.Column(db.BigInteger, nullable=True)
    bank_swift_number = db.Column(db.String(50), server_default='', default='', nullable=True)
    bank_iban_number = db.Column(db.String(50), server_default='', default='', nullable=True)

    is_bank_account = db.Column(db.Boolean, server_default=db.text('false'), default=False, nullable=False)
    is_payment_enabled = db.Column(db.Boolean, server_default=db.text('false'), default=False, nullable=False)
    is_deposit = db.Column(db.Boolean, server_default=db.text('false'), default=False, nullable=False)
    is_archived = db.Column(db.Boolean, server_default=db.text('false'), default=False, nullable=False)
