from typing import TYPE_CHECKING

# from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, relationship

from .base import BaseModel, db

if TYPE_CHECKING:
    from .invoice_setting import InvoiceSetting


COMPANY_FORMS = ("enkeltmandsvirksomhed", "aps")
# How often the organization files its VAT return (docs/vat-design.md)
VAT_PERIOD_TYPES = ("half_year", "quarter", "month")


class Organization(BaseModel):
    __tablename__ = "organizations"
    __table_args__ = (
        db.CheckConstraint(
            "company_form IN ('enkeltmandsvirksomhed', 'aps')",
            name="ck_organizations_company_form",
        ),
        db.CheckConstraint(
            "vat_period_type IS NULL OR "
            "vat_period_type IN ('half_year', 'quarter', 'month')",
            name="ck_organizations_vat_period_type",
        ),
    )

    id = db.Column(
        db.Integer, autoincrement=True, primary_key=True, nullable=False
    )

    """
    Primary keys: id
    """

    registration_no = db.Column(
        db.String(50), server_default="", default="", nullable=True
    )
    name = db.Column(db.String(100), unique=True, nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)

    # Decides the equity accounts and the year-end closing
    # (docs/chart-of-accounts.md)
    company_form = db.Column(
        db.String(30),
        server_default="enkeltmandsvirksomhed",
        default="enkeltmandsvirksomhed",
        nullable=False,
    )

    # Null when the organization is not VAT-registered: it uses no VAT codes
    vat_period_type = db.Column(db.String(10), nullable=True)

    logo = db.Column(db.String(255), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    street = db.Column(db.String(100), nullable=True)
    zipcode = db.Column(db.String(10), nullable=True)
    city = db.Column(db.String(50), nullable=True)
    country_id = db.Column(
        db.Integer, db.ForeignKey("countries.id"), nullable=False
    )

    invoice_setting: Mapped["InvoiceSetting"] = relationship(
        "InvoiceSetting", back_populates="organization", uselist=False
    )
    country = db.relationship("Country", backref="organizations")
    users = db.relationship(
        "User", backref="organizations", cascade="all, delete"
    )

    def __repr__(self):
        return f"<Organization {self.id}, {self.name}>"
