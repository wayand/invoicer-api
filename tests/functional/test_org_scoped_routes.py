"""
Every route with an organization id in its path must treat a user of another
organization as a stranger: 404, as if the organization did not exist.

Each route is checked twice against a second organization's real data (its
contact, invoice and invoice line): a stranger gets 404, and the owner does
not, so the 404 is about permission and not about a missing id. A route that
is added later must be listed here, which makes it get the same check.
"""

import re
from datetime import date

import pytest
from flask_jwt_extended import create_access_token

from app.models.contact import Contact
from app.models.invoice import Invoice
from app.models.invoiceline import InvoiceLine
from app.models.organization import Organization
from app.models.product import Product
from app.models.user import User

ORG_SCOPED_ROUTES = [
    ("DELETE", "/organizations/{organization_id}"),
    ("GET", "/organizations/{organization_id}"),
    ("PUT", "/organizations/{organization_id}"),
    ("GET", "/organizations/{organization_id}/contacts"),
    ("POST", "/organizations/{organization_id}/contacts"),
    ("DELETE", "/organizations/{organization_id}/contacts/{contact_id}"),
    ("GET", "/organizations/{organization_id}/contacts/{contact_id}"),
    ("PUT", "/organizations/{organization_id}/contacts/{contact_id}"),
    ("POST", "/organizations/{organization_id}/invoices"),
    ("DELETE", "/organizations/{organization_id}/invoices/{invoice_id}"),
    ("PUT", "/organizations/{organization_id}/invoices/{invoice_id}"),
    (
        "GET",
        "/organizations/{organization_id}/invoices/{invoice_id}/invoice-lines",
    ),
    (
        "DELETE",
        "/organizations/{organization_id}/invoices/{invoice_id}/invoice-lines/{line_id}",
    ),
    (
        "GET",
        "/organizations/{organization_id}/invoices/{invoice_id}/invoice-lines/{line_id}",
    ),
    ("POST", "/organizations/{organization_id}/upload-logo"),
]


def headers_for(user) -> dict:
    token = create_access_token(
        identity=user.email, additional_claims={"tv": user.token_version}
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def org_b(db_session, country):
    org = Organization(
        name="Organization B ApS",
        slug="organization-b",
        country_id=country.id,
        email="b@example.com",
        logo="",
    )
    db_session.add(org)
    db_session.commit()
    return org


@pytest.fixture
def owner_b(db_session, org_b) -> User:
    user = User(
        organization_id=org_b.id,
        email="owner-b@example.com",
        name="Owner of B",
        password_plaintext="password123",
        otp_secret=User.generate_otp_secret(),
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def ids_b(db_session, org_b, country) -> dict:
    """Real ids inside organization B, to fill the route templates."""
    contact = Contact(
        organization_id=org_b.id,
        name="Client of B",
        email="client-b@example.com",
        country_id=country.id,
    )
    product = Product(
        organization_id=org_b.id, name="Product of B", unit_price=10
    )
    db_session.add_all([contact, product])
    db_session.commit()
    invoice = Invoice(
        organization_id=org_b.id,
        contact_id=contact.id,
        invoice_no="1",
        invoice_date=date(2026, 1, 1),
        duedate=date(2026, 1, 15),
        amount=100,
        vat_amount=25,
        gross_amount=125,
        lines=[
            InvoiceLine(
                product_id=product.id,
                description="Work",
                quantity=1,
                unit_price=100,
                amount=100,
            )
        ],
    )
    db_session.add(invoice)
    db_session.commit()
    return {
        "organization_id": org_b.id,
        "contact_id": contact.id,
        "invoice_id": invoice.id,
        "line_id": invoice.lines[0].id,
    }


def request_as(client, user, method, template, ids):
    url = template.format(**ids)
    kwargs = {"headers": headers_for(user)}
    if method in ("POST", "PUT", "PATCH"):
        kwargs["json"] = {}
    return client.open(url, method=method, **kwargs)


def test_every_organization_scoped_route_is_listed_here(app):
    found = {
        (method, re.sub(r"<int:(\w+)>", r"{\1}", rule.rule))
        for rule in app.url_map.iter_rules()
        if "organization_id" in rule.arguments
        for method in rule.methods - {"HEAD", "OPTIONS"}
    }

    assert found - set(ORG_SCOPED_ROUTES) == set(), (
        "new route(s) with an organization id: add them to ORG_SCOPED_ROUTES"
    )
    assert set(ORG_SCOPED_ROUTES) - found == set(), (
        "listed route(s) that no longer exist: remove them from ORG_SCOPED_ROUTES"
    )


@pytest.mark.parametrize("method,template", ORG_SCOPED_ROUTES)
def test_a_stranger_gets_404_and_the_owner_does_not(
    client, test_user, owner_b, ids_b, method, template
):
    stranger = request_as(client, test_user, method, template, ids_b)
    owner = request_as(client, owner_b, method, template, ids_b)

    assert stranger.status_code == 404, (
        f"{method} {template}: a user of another organization got "
        f"{stranger.status_code}"
    )
    assert owner.status_code not in (401, 403, 404), (
        f"{method} {template}: the owner got {owner.status_code}, "
        "so the ids in this test do not reach the route"
    )


def test_a_stranger_cannot_change_another_organization(
    client, db_session, test_user, org_b, country
):
    res = client.put(
        f"/organizations/{org_b.id}",
        json={
            "name": "Hijacked Company ApS",
            "slug": "hijacked",
            "email": "hijacked@example.com",
            "country_id": country.id,
        },
        headers=headers_for(test_user),
    )

    assert res.status_code == 404
    db_session.refresh(org_b)
    assert (org_b.name, org_b.slug, org_b.email) == (
        "Organization B ApS",
        "organization-b",
        "b@example.com",
    )


def test_a_member_can_still_update_their_own_organization(
    client, db_session, test_user, organization, country
):
    res = client.put(
        f"/organizations/{organization.id}",
        json={
            "name": "Renamed Company ApS",
            "slug": organization.slug,
            "email": organization.email,
            "country_id": country.id,
        },
        headers=headers_for(test_user),
    )

    assert res.status_code == 200, res.get_json()
    db_session.refresh(organization)
    assert organization.name == "Renamed Company ApS"


def test_updating_an_organization_that_does_not_exist_is_404(
    client, test_user, country
):
    res = client.put(
        "/organizations/999999",
        json={
            "name": "Nobody Ltd",
            "email": "n@example.com",
            "country_id": country.id,
        },
        headers=headers_for(test_user),
    )

    assert res.status_code == 404


def test_updating_an_organization_requires_authentication(client, organization):
    res = client.put(f"/organizations/{organization.id}", json={})

    assert res.status_code == 401
