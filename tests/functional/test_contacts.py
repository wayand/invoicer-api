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


# ------------------------------------------------ empty optional fields

OPTIONAL_TEXT_FIELDS = [
    "logo",
    "phone",
    "street",
    "zipcode",
    "city",
    "contactperson_name",
    "contactperson_email",
]


def fetch_contact(client, user, organization, contact_id) -> dict:
    res = client.get(
        f"/organizations/{organization.id}/contacts/{contact_id}",
        headers=auth_headers(user),
    )
    assert res.status_code == 200
    return res.get_json()


def test_a_contact_can_be_saved_back_as_the_api_returned_it(
    client, test_user, organization, country
):
    """What the edit form does: load the contact and send it back. Fields
    that were never filled in come back as null and must be accepted."""
    created = create_contact(client, test_user, organization, country)
    shown = fetch_contact(client, test_user, organization, created["id"])
    assert shown["phone"] is None  # the premise: the API returns null

    for dump_only in ("id", "created_at", "updated_at"):
        shown.pop(dump_only)
    shown["city"] = "Aarhus"  # the user changes one field
    res = client.put(
        f"/organizations/{organization.id}/contacts/{created['id']}",
        json=shown,
        headers=auth_headers(test_user),
    )

    assert res.status_code == 200, res.get_json()
    assert stored(created["id"]).city == "Aarhus"
    assert stored(created["id"]).phone is None


@pytest.mark.parametrize("field", OPTIONAL_TEXT_FIELDS)
def test_update_accepts_null_for_an_optional_field_and_clears_it(
    client, test_user, organization, country, field
):
    value = "x@example.com" if field.endswith("email") else "something"
    created = create_contact(
        client, test_user, organization, country, **{field: value}
    )

    res = update_contact(
        client, test_user, organization, created["id"], **{field: None}
    )

    assert res.status_code == 200, res.get_json()
    assert getattr(stored(created["id"]), field) is None


@pytest.mark.parametrize("field", OPTIONAL_TEXT_FIELDS)
def test_create_accepts_null_for_an_optional_field(
    client, test_user, organization, country, field
):
    res = client.post(
        f"/organizations/{organization.id}/contacts",
        json={
            "name": "Acme",
            "email": "acme@example.com",
            "country_id": country.id,
            field: None,
        },
        headers=auth_headers(test_user),
    )

    assert res.status_code == 201, res.get_json()
    assert getattr(stored(res.get_json()["id"]), field) is None


@pytest.mark.parametrize(
    "field", ["name", "email", "is_company", "registration_no"]
)
def test_required_fields_still_reject_null(
    client, test_user, organization, country, field
):
    """name and email are required; registration_no is part of the primary
    key, so it can't be null either."""
    created = create_contact(client, test_user, organization, country)

    res = update_contact(
        client, test_user, organization, created["id"], **{field: None}
    )

    assert res.status_code == 422
    assert field in res.get_json()["errors"]
