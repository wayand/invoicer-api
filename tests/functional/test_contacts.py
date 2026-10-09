"""
Contact create/update: the company-vs-private flag (`is_company`) must be
stored on create and changeable on update. `type` is a separate field (the
contact's role, default "client") and must not be confused with it.
"""

import pytest
from flask_jwt_extended import create_access_token

from app.models.contact import Contact


def auth_headers(user) -> dict:
    return {
        "Authorization": f"Bearer {create_access_token(identity=user.email)}"
    }


def create_contact(client, user, organization, country, **extra) -> dict:
    res = client.post(
        f"/organizations/{organization.id}/contacts",
        json={
            "name": "Acme",
            "email": "acme@example.com",
            "country_id": country.id,
            **extra,
        },
        headers=auth_headers(user),
    )
    assert res.status_code == 201
    return res.get_json()


def update_contact(client, user, organization, contact_id, **fields):
    return client.put(
        f"/organizations/{organization.id}/contacts/{contact_id}",
        json={"name": "Acme", "email": "acme@example.com", **fields},
        headers=auth_headers(user),
    )


def stored(contact_id) -> Contact:
    return Contact.query.filter_by(id=contact_id).one()


@pytest.mark.parametrize("flag", [True, False])
def test_create_stores_is_company(
    client, test_user, organization, country, flag
):
    created = create_contact(
        client, test_user, organization, country, is_company=flag
    )
    assert created["is_company"] is flag
    assert stored(created["id"]).is_company is flag


@pytest.mark.parametrize("before, after", [(True, False), (False, True)])
def test_update_changes_is_company(
    client, test_user, organization, country, before, after
):
    created = create_contact(
        client, test_user, organization, country, is_company=before
    )

    res = update_contact(
        client, test_user, organization, created["id"], is_company=after
    )

    assert res.status_code == 200
    assert res.get_json()["is_company"] is after
    assert stored(created["id"]).is_company is after


def test_update_without_is_company_leaves_it_unchanged(
    client, test_user, organization, country
):
    created = create_contact(
        client, test_user, organization, country, is_company=True
    )

    res = update_contact(
        client, test_user, organization, created["id"], phone="12345678"
    )

    assert res.status_code == 200
    assert stored(created["id"]).is_company is True
    assert stored(created["id"]).phone == "12345678"


def test_is_company_does_not_touch_the_contact_type(
    client, test_user, organization, country
):
    created = create_contact(
        client, test_user, organization, country, is_company=True
    )
    assert created["type"] == "client"

    res = update_contact(
        client, test_user, organization, created["id"], is_company=False
    )

    assert res.status_code == 200
    assert stored(created["id"]).type == "client"


def test_update_rejects_non_boolean_is_company(
    client, test_user, organization, country
):
    created = create_contact(
        client, test_user, organization, country, is_company=True
    )

    res = update_contact(
        client, test_user, organization, created["id"], is_company="banana"
    )

    assert res.status_code == 422
    assert "is_company" in res.get_json()["errors"]
    assert stored(created["id"]).is_company is True
