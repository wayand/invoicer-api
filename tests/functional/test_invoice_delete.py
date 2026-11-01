"""
Only a draft can be deleted. Once an invoice is approved, sent or paid it is
part of the books: deleting it would leave a gap in the numbering, so the API
refuses (409) whatever the client does.
"""

from datetime import date

import pytest
from flask_jwt_extended import create_access_token

from app.models.contact import Contact
from app.models.invoice import Invoice
from app.models.invoiceline import InvoiceLine
from app.models.product import Product
from app.models.vat_code import VatCode


def auth_headers(user) -> dict:
    return {
        "Authorization": f"Bearer {create_access_token(identity=user.email)}"
    }


@pytest.fixture
def contact(db_session, organization, country) -> Contact:
    contact = Contact(
        organization_id=organization.id,
        name="Client",
        email="client@example.com",
        country_id=country.id,
    )
    db_session.add(contact)
    db_session.commit()
    return contact


@pytest.fixture
def product(db_session, organization) -> Product:
    product = Product(
        organization_id=organization.id, name="Consulting", unit_price=100
    )
    db_session.add(product)
    db_session.commit()
    return product


@pytest.fixture
def make_invoice(db_session, organization, contact, product):
    """Factory: a draft invoice with two lines; extra keyword arguments set
    other fields."""

    def make(invoice_no="1001", **fields) -> Invoice:
        invoice = Invoice(
            organization_id=organization.id,
            contact_id=contact.id,
            invoice_no=invoice_no,
            invoice_date=date(2026, 1, 1),
            duedate=date(2026, 1, 15),
            amount=200,
            vat_amount=50,
            gross_amount=250,
            lines=[
                InvoiceLine(
                    product_id=product.id,
                    vat_code_id=VatCode.query.filter_by(code="S01").one().id,
                    description=f"Work {n}",
                    quantity=1,
                    unit_price=100,
                    amount=100,
                )
                for n in (1, 2)
            ],
            **fields,
        )
        db_session.add(invoice)
        db_session.commit()
        return invoice

    return make


def delete(client, user, organization, invoice_id):
    return client.delete(
        f"/organizations/{organization.id}/invoices/{invoice_id}",
        headers=auth_headers(user),
    )


def test_a_draft_invoice_is_deleted_with_its_lines(
    client, test_user, organization, make_invoice
):
    invoice = make_invoice()

    res = delete(client, test_user, organization, invoice.id)

    assert res.status_code == 200
    assert Invoice.query.filter_by(invoice_no="1001").count() == 0
    assert InvoiceLine.query.count() == 0


def test_deleting_a_draft_leaves_the_other_invoices_alone(
    client, test_user, organization, make_invoice
):
    doomed = make_invoice("1001")
    make_invoice("1002")

    delete(client, test_user, organization, doomed.id)

    assert [i.invoice_no for i in Invoice.query.all()] == ["1002"]
    assert InvoiceLine.query.count() == 2


def test_deleting_an_invoice_that_does_not_exist_is_a_404(
    client, test_user, organization
):
    res = delete(client, test_user, organization, 99999)

    assert res.status_code == 404


def test_deleting_an_invoice_requires_authentication(
    client, organization, make_invoice
):
    invoice = make_invoice()

    res = client.delete(
        f"/organizations/{organization.id}/invoices/{invoice.id}"
    )

    assert res.status_code == 401
    assert Invoice.query.filter_by(id=invoice.id).count() == 1
