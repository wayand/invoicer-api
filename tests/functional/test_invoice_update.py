"""
Saving an invoice changes the fields that were sent and nothing else. In
particular the template is only changed by template_id: sending is_sent must
never end up in the template.
"""

from datetime import date

import pytest
from flask_jwt_extended import create_access_token

from app.models.contact import Contact
from app.models.invoice import Invoice
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


def body(organization, contact, product, **overrides) -> dict:
    body = {
        "organization_id": organization.id,
        "contact_id": contact.id,
        "invoice_no": "1001",
        "currency_id": "DKK",
        "state": "draft",
        "invoice_date": date(2026, 1, 1).isoformat(),
        "duedate": date(2026, 1, 15).isoformat(),
        "lines": [
            {
                "product_id": product.id,
                "description": "Work",
                "vat_code": "S01",
                "quantity": 1,
                "unit_price": 100,
            }
        ],
    }
    body.update(overrides)
    return body


@pytest.fixture
def invoice(
    client, test_user, organization, contact, product, invoice_setting
) -> dict:
    """An invoice created through the API on template 2, as the API returns it."""
    res = client.post(
        f"/organizations/{organization.id}/invoices",
        json=body(organization, contact, product, template_id="2"),
        headers=auth_headers(test_user),
    )
    assert res.status_code == 201, res.get_json()
    return res.get_json()


def update(client, user, organization, invoice, contact, product, **overrides):
    # As the app sends it: the line as returned, without its timestamps and
    # amount (the server calculates it)
    line = {
        key: value
        for key, value in invoice["lines"][0].items()
        if key not in ("created_at", "updated_at", "amount")
    }
    line["description"] = "Changed"
    return client.put(
        f"/organizations/{organization.id}/invoices/{invoice['id']}",
        json=body(organization, contact, product, lines=[line], **overrides),
        headers=auth_headers(user),
    )


def stored_template(invoice) -> str:
    return Invoice.query.filter_by(id=invoice["id"]).one().template_id


def test_the_invoice_starts_on_the_template_it_was_created_with(invoice):
    assert stored_template(invoice) == "2"


@pytest.mark.parametrize("is_sent", [True, False])
def test_update_keeps_the_template_when_only_is_sent_is_sent(
    client, test_user, organization, contact, product, invoice, is_sent
):
    res = update(
        client,
        test_user,
        organization,
        invoice,
        contact,
        product,
        is_sent=is_sent,
    )

    assert res.status_code == 200, res.get_json()
    assert stored_template(invoice) == "2"
    assert res.get_json()["template_id"] == "2"


def test_update_keeps_the_template_when_none_is_sent(
    client, test_user, organization, contact, product, invoice
):
    res = update(client, test_user, organization, invoice, contact, product)

    assert res.status_code == 200, res.get_json()
    assert stored_template(invoice) == "2"


def test_update_changes_the_template_when_one_is_sent(
    client, test_user, organization, contact, product, invoice
):
    res = update(
        client,
        test_user,
        organization,
        invoice,
        contact,
        product,
        template_id="3",
    )

    assert res.status_code == 200, res.get_json()
    assert stored_template(invoice) == "3"
    assert res.get_json()["template_id"] == "3"


def test_update_still_saves_is_sent(
    client, test_user, organization, contact, product, invoice
):
    res = update(
        client,
        test_user,
        organization,
        invoice,
        contact,
        product,
        is_sent=True,
    )

    assert res.status_code == 200, res.get_json()
    assert res.get_json()["is_sent"] is True
    assert Invoice.query.filter_by(id=invoice["id"]).one().is_sent is True
