"""
Creating an invoice is all-or-nothing: either the invoice is saved and the
organization's next invoice number is advanced, or neither happens and the
caller gets an error. It must never answer with an error while the invoice
is already in the database.
"""

from datetime import date

import pytest
from flask_jwt_extended import create_access_token

from app.models.contact import Contact
from app.models.invoice import Invoice
from app.models.invoiceline import InvoiceLine
from app.models.product import Product


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


def payload(organization, contact, product, invoice_no) -> dict:
    return {
        "organization_id": organization.id,
        "contact_id": contact.id,
        "invoice_no": invoice_no,
        "currency_id": "DKK",
        "state": "draft",
        "amount": 100,
        "vat_amount": 25,
        "gross_amount": 125,
        "invoice_date": date(2026, 1, 1).isoformat(),
        "duedate": date(2026, 1, 15).isoformat(),
        "lines": [
            {
                "product_id": product.id,
                "description": "Work",
                "quantity": 1,
                "unit_price": 100,
                "amount": 100,
            }
        ],
    }


def post_invoice(client, user, organization, contact, product, invoice_no):
    return client.post(
        f"/organizations/{organization.id}/invoices",
        json=payload(organization, contact, product, invoice_no),
        headers=auth_headers(user),
    )


def invoices_numbered(invoice_no) -> list:
    return Invoice.query.filter_by(invoice_no=invoice_no).all()


def next_number(db_session, invoice_setting) -> int:
    db_session.refresh(invoice_setting)
    return invoice_setting.next_invoice_no


def test_create_invoice_succeeds_and_advances_the_next_number(
    client,
    db_session,
    test_user,
    organization,
    contact,
    product,
    invoice_setting,
):
    res = post_invoice(
        client, test_user, organization, contact, product, "1001"
    )

    assert res.status_code == 201
    assert len(invoices_numbered("1001")) == 1
    assert InvoiceLine.query.count() == 1
    assert next_number(db_session, invoice_setting) == 1002


def test_create_invoice_keeps_the_next_number_for_non_numeric_numbers(
    client,
    db_session,
    test_user,
    organization,
    contact,
    product,
    invoice_setting,
):
    before = next_number(db_session, invoice_setting)

    res = post_invoice(
        client, test_user, organization, contact, product, "INV-7"
    )

    assert res.status_code == 201
    assert len(invoices_numbered("INV-7")) == 1
    assert next_number(db_session, invoice_setting) == before


def test_create_invoice_without_settings_saves_nothing(
    client, test_user, organization, contact, product
):
    res = post_invoice(
        client, test_user, organization, contact, product, "1001"
    )

    assert res.status_code == 409
    assert invoices_numbered("1001") == []
    assert InvoiceLine.query.count() == 0


def test_create_invoice_without_settings_says_what_is_missing(
    client, test_user, organization, contact, product
):
    res = post_invoice(
        client, test_user, organization, contact, product, "1001"
    )

    assert "invoice settings" in res.get_json()["error"].lower()


def test_create_invoice_rolls_back_when_a_later_step_fails(
    client,
    db_session,
    test_user,
    organization,
    contact,
    product,
    invoice_setting,
    monkeypatch,
):
    def boom(_invoice_no):
        raise RuntimeError("simulated failure after the invoice was added")

    monkeypatch.setattr("app.routes.invoice_routes._following_invoice_no", boom)
    before = next_number(db_session, invoice_setting)

    res = post_invoice(
        client, test_user, organization, contact, product, "1001"
    )

    assert res.status_code == 400
    assert invoices_numbered("1001") == []
    assert InvoiceLine.query.count() == 0
    assert next_number(db_session, invoice_setting) == before


def test_create_invoice_rejects_a_duplicate_number_and_changes_nothing(
    client,
    db_session,
    test_user,
    organization,
    contact,
    product,
    invoice_setting,
):
    first = post_invoice(
        client, test_user, organization, contact, product, "1001"
    )
    assert first.status_code == 201

    again = post_invoice(
        client, test_user, organization, contact, product, "1001"
    )

    assert again.status_code == 400
    assert len(invoices_numbered("1001")) == 1
    assert next_number(db_session, invoice_setting) == 1002


def test_create_invoice_requires_authentication(client, organization):
    res = client.post(
        f"/organizations/{organization.id}/invoices", json={"lines": []}
    )

    assert res.status_code == 401
