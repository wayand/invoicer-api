"""
Tenant isolation: a user of organization A must never read, modify or create
data that belongs to organization B, whatever organization id the request
puts in the URL or the JSON body.
"""

from datetime import date

import pytest
from flask_jwt_extended import create_access_token

from app.models.account import Account, AccountGroup, AccountType
from app.models.contact import Contact
from app.models.invoice import Invoice
from app.models.invoice_setting import InvoiceSetting
from app.models.invoiceline import InvoiceLine
from app.models.organization import Organization
from app.models.product import Product
from app.models.user import User


def auth_headers(user: User) -> dict:
    return {
        "Authorization": f"Bearer {create_access_token(identity=user.email)}"
    }


@pytest.fixture
def org_b(db_session, country) -> Organization:
    org = Organization(
        name="Other ApS",
        slug="other-aps",
        country_id=country.id,
        email="other@example.com",
        logo="",
    )
    db_session.add(org)
    db_session.commit()
    return org


@pytest.fixture
def contact_a(db_session, organization, country) -> Contact:
    contact = Contact(
        organization_id=organization.id,
        name="Client of A",
        email="client-a@example.com",
        country_id=country.id,
    )
    db_session.add(contact)
    db_session.commit()
    return contact


@pytest.fixture
def contact_b(db_session, org_b, country) -> Contact:
    contact = Contact(
        organization_id=org_b.id,
        name="Secret client of B",
        email="client-b@example.com",
        country_id=country.id,
    )
    db_session.add(contact)
    db_session.commit()
    return contact


@pytest.fixture
def product_b(db_session, org_b) -> Product:
    product = Product(
        organization_id=org_b.id, name="Product of B", unit_price=10
    )
    db_session.add(product)
    db_session.commit()
    return product


def make_invoice_setting(db_session, org: Organization) -> InvoiceSetting:
    account_type = AccountType(
        organization_id=org.id,
        name="Revenue",
        normal_balance="credit",
        report_type="income",
    )
    db_session.add(account_type)
    db_session.flush()
    group = AccountGroup(
        organization_id=org.id,
        account_type_id=account_type.id,
        name="Sales",
        number=1,
        interval_start=1000,
        interval_end=1999,
    )
    db_session.add(group)
    db_session.flush()
    account = Account(
        organization_id=org.id,
        account_type_id=account_type.id,
        account_group_id=group.id,
        name="Sales of services",
        number=1000,
    )
    db_session.add(account)
    db_session.flush()
    setting = InvoiceSetting(
        organization_id=org.id,
        default_account_id=account.id,
        default_deposit_account_id=account.id,
        next_invoice_no=1,
    )
    db_session.add(setting)
    db_session.commit()
    return setting


@pytest.fixture
def invoice_setting_a(db_session, organization) -> InvoiceSetting:
    return make_invoice_setting(db_session, organization)


@pytest.fixture
def invoice_setting_b(db_session, org_b) -> InvoiceSetting:
    return make_invoice_setting(db_session, org_b)


@pytest.fixture
def product_a(db_session, organization) -> Product:
    product = Product(
        organization_id=organization.id, name="Product of A", unit_price=10
    )
    db_session.add(product)
    db_session.commit()
    return product


@pytest.fixture
def invoice_b(db_session, org_b, contact_b, product_b) -> Invoice:
    invoice = Invoice(
        organization_id=org_b.id,
        invoice_no="9001",
        contact_id=contact_b.id,
        currency_id="DKK",
        state="draft",
        amount=100,
        vat_amount=25,
        gross_amount=125,
        invoice_date=date(2026, 1, 1),
        duedate=date(2026, 1, 15),
    )
    db_session.add(invoice)
    db_session.flush()
    db_session.add(
        InvoiceLine(
            invoice_id=invoice.id,
            product_id=product_b.id,
            description="Line of B",
            quantity=1,
            unit_price=100,
            amount=100,
        )
    )
    db_session.commit()
    return invoice


def invoice_payload(organization_id: int, contact_id: int, product_id: int):
    return {
        "organization_id": organization_id,
        "contact_id": contact_id,
        "invoice_no": "5000",
        "currency_id": "DKK",
        "state": "draft",
        "amount": 100,
        "vat_amount": 25,
        "gross_amount": 125,
        "invoice_date": "2026-01-01",
        "duedate": "2026-01-15",
        "lines": [
            {
                "product_id": product_id,
                "description": "Work",
                "quantity": 1,
                "unit_price": 100,
                "amount": 100,
            }
        ],
    }


# ---------------------------------------------------------------- contacts


def test_own_contacts_are_still_accessible(
    client, test_user, organization, contact_a
):
    res = client.get(
        f"/organizations/{organization.id}/contacts",
        headers=auth_headers(test_user),
    )
    assert res.status_code == 200
    assert [c["name"] for c in res.get_json()] == ["Client of A"]


def test_cannot_list_contacts_of_another_org(
    client, test_user, org_b, contact_b
):
    res = client.get(
        f"/organizations/{org_b.id}/contacts", headers=auth_headers(test_user)
    )
    assert res.status_code == 404
    assert b"Secret client of B" not in res.data


def test_cannot_read_contact_of_another_org(
    client, test_user, org_b, contact_b
):
    res = client.get(
        f"/organizations/{org_b.id}/contacts/{contact_b.id}",
        headers=auth_headers(test_user),
    )
    assert res.status_code == 404
    assert b"Secret client of B" not in res.data


def test_cannot_update_contact_of_another_org(
    client, db_session, test_user, org_b, contact_b
):
    res = client.put(
        f"/organizations/{org_b.id}/contacts/{contact_b.id}",
        json={"name": "Hijacked", "email": "evil@example.com"},
        headers=auth_headers(test_user),
    )
    assert res.status_code == 404
    db_session.refresh(contact_b)
    assert contact_b.name == "Secret client of B"


def test_cannot_delete_contact_of_another_org(
    client, db_session, test_user, org_b, contact_b
):
    res = client.delete(
        f"/organizations/{org_b.id}/contacts/{contact_b.id}",
        headers=auth_headers(test_user),
    )
    assert res.status_code == 404
    assert Contact.query.filter_by(id=contact_b.id).first() is not None


def test_cannot_create_contact_in_another_org_via_url(
    client, test_user, org_b, country
):
    res = client.post(
        f"/organizations/{org_b.id}/contacts",
        json={
            "name": "Planted",
            "email": "planted@example.com",
            "organization_id": org_b.id,
            "country_id": country.id,
        },
        headers=auth_headers(test_user),
    )
    assert res.status_code == 404
    assert Contact.query.filter_by(name="Planted").first() is None


def test_contact_body_organization_id_is_ignored(
    client, test_user, organization, org_b, country
):
    res = client.post(
        f"/organizations/{organization.id}/contacts",
        json={
            "name": "Smuggled",
            "email": "smuggled@example.com",
            "organization_id": org_b.id,
            "country_id": country.id,
        },
        headers=auth_headers(test_user),
    )
    assert res.status_code == 201
    created = Contact.query.filter_by(name="Smuggled").one()
    assert created.organization_id == organization.id


# --------------------------------------------------------------- products


def test_product_body_organization_id_is_ignored(
    client, test_user, organization, org_b
):
    res = client.post(
        "/products",
        json={
            "name": "Smuggled product",
            "description": "should land in my own org",
            "unit_price": 5,
            "archived": False,
            "organization_id": org_b.id,
        },
        headers=auth_headers(test_user),
    )
    assert res.status_code == 201
    created = Product.query.filter_by(name="Smuggled product").one()
    assert created.organization_id == organization.id


# --------------------------------------------------------------- invoices


def test_cannot_update_invoice_of_another_org(
    client, db_session, test_user, org_b, invoice_b, contact_b, product_b
):
    res = client.put(
        f"/organizations/{org_b.id}/invoices/{invoice_b.id}",
        json=invoice_payload(org_b.id, contact_b.id, product_b.id),
        headers=auth_headers(test_user),
    )
    assert res.status_code == 404
    db_session.refresh(invoice_b)
    assert invoice_b.invoice_no == "9001"


def test_cannot_delete_invoice_of_another_org(
    client, db_session, test_user, org_b, invoice_b
):
    res = client.delete(
        f"/organizations/{org_b.id}/invoices/{invoice_b.id}",
        headers=auth_headers(test_user),
    )
    assert res.status_code == 404
    assert Invoice.query.filter_by(id=invoice_b.id).first() is not None


def test_cannot_create_invoice_in_another_org(
    client, test_user, org_b, contact_b, product_b
):
    res = client.post(
        f"/organizations/{org_b.id}/invoices",
        json=invoice_payload(org_b.id, contact_b.id, product_b.id),
        headers=auth_headers(test_user),
    )
    assert res.status_code == 404
    assert Invoice.query.filter_by(invoice_no="5000").first() is None


def test_cannot_read_invoice_lines_of_another_org(
    client, test_user, org_b, invoice_b
):
    res = client.get(
        f"/organizations/{org_b.id}/invoices/{invoice_b.id}/invoice-lines",
        headers=auth_headers(test_user),
    )
    assert res.status_code == 404
    assert b"Line of B" not in res.data


def test_cannot_delete_invoice_line_of_another_org(
    client, db_session, test_user, org_b, invoice_b
):
    line = InvoiceLine.query.filter_by(invoice_id=invoice_b.id).one()
    res = client.delete(
        f"/organizations/{org_b.id}/invoices/{invoice_b.id}/invoice-lines/{line.id}",
        headers=auth_headers(test_user),
    )
    assert res.status_code == 404
    assert db_session.get(InvoiceLine, line.id) is not None


def test_own_org_can_create_invoice(
    client, test_user, organization, contact_a, product_a, invoice_setting_a
):
    res = client.post(
        f"/organizations/{organization.id}/invoices",
        json=invoice_payload(organization.id, contact_a.id, product_a.id),
        headers=auth_headers(test_user),
    )
    assert res.status_code == 201
    assert Invoice.query.filter_by(invoice_no="5000").one().organization_id == (
        organization.id
    )


def test_invoice_body_organization_id_is_ignored(
    client,
    test_user,
    organization,
    org_b,
    contact_a,
    product_a,
    invoice_setting_a,
):
    res = client.post(
        f"/organizations/{organization.id}/invoices",
        json=invoice_payload(org_b.id, contact_a.id, product_a.id),
        headers=auth_headers(test_user),
    )
    assert res.status_code == 201
    invoice = Invoice.query.filter_by(invoice_no="5000").one()
    assert invoice.organization_id == organization.id


def test_invoice_cannot_reference_contact_of_another_org(
    client,
    test_user,
    organization,
    contact_b,
    product_a,
    invoice_setting_a,
):
    res = client.post(
        f"/organizations/{organization.id}/invoices",
        json=invoice_payload(organization.id, contact_b.id, product_a.id),
        headers=auth_headers(test_user),
    )
    assert res.status_code == 404
    assert b"Secret client of B" not in res.data
    assert Invoice.query.filter_by(invoice_no="5000").first() is None


def test_invoice_cannot_reference_product_of_another_org(
    client,
    test_user,
    organization,
    contact_a,
    product_b,
    invoice_setting_a,
):
    res = client.post(
        f"/organizations/{organization.id}/invoices",
        json=invoice_payload(organization.id, contact_a.id, product_b.id),
        headers=auth_headers(test_user),
    )
    assert res.status_code == 404
    assert Invoice.query.filter_by(invoice_no="5000").first() is None


def test_invoice_update_cannot_reference_contact_of_another_org(
    client,
    db_session,
    test_user,
    organization,
    contact_a,
    contact_b,
    product_a,
    invoice_setting_a,
):
    created = client.post(
        f"/organizations/{organization.id}/invoices",
        json=invoice_payload(organization.id, contact_a.id, product_a.id),
        headers=auth_headers(test_user),
    )
    assert created.status_code == 201
    invoice_id = created.get_json()["id"]

    res = client.put(
        f"/organizations/{organization.id}/invoices/{invoice_id}",
        json=invoice_payload(organization.id, contact_b.id, product_a.id),
        headers=auth_headers(test_user),
    )
    assert res.status_code == 404
    assert b"Secret client of B" not in res.data
    assert (
        Invoice.query.filter_by(id=invoice_id).one().contact_id == contact_a.id
    )


# ------------------------------------------------------- invoice settings


def test_invoice_setting_body_organization_id_is_ignored(
    client,
    db_session,
    test_user,
    organization,
    org_b,
    invoice_setting_a,
    invoice_setting_b,
):
    res = client.put(
        "/invoice-setting",
        json={
            "organization_id": org_b.id,
            "template_id": "1",
            "invoice_no_mode": "manual",
            "next_invoice_no": 777,
            "default_reminder_fee": 0,
        },
        headers=auth_headers(test_user),
    )
    assert res.status_code in (200, 201)
    db_session.refresh(invoice_setting_a)
    db_session.refresh(invoice_setting_b)
    assert invoice_setting_a.organization_id == organization.id
    assert invoice_setting_a.next_invoice_no == 777
    assert invoice_setting_b.organization_id == org_b.id
    assert invoice_setting_b.next_invoice_no == 1
