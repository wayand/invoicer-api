"""
Saving the organization form: fields that were never filled in come back from
the API as null, and the form sends them back as they are, so the API has to
accept null for the optional ones (and only for those).
"""

import pytest
from flask_jwt_extended import create_access_token

from app.models.organization import Organization

OPTIONAL_FIELDS = [
    "logo",
    "phone",
    "street",
    "zipcode",
    "city",
    "registration_no",
]


def auth_headers(user) -> dict:
    return {
        "Authorization": f"Bearer {create_access_token(identity=user.email)}"
    }


def stored(organization) -> Organization:
    return Organization.query.filter_by(id=organization.id).one()


def form_payload(client, user, organization) -> dict:
    """What the edit form sends: the organization as the API returned it,
    without what the form never sends back."""
    res = client.get(
        f"/organizations/{organization.id}", headers=auth_headers(user)
    )
    assert res.status_code == 200
    body = res.get_json()
    for dropped in (
        "id",
        "created_at",
        "updated_at",
        "country",
        "users",
        "invoice_setting",
    ):
        body.pop(dropped, None)
    return body


def put(client, user, organization, body):
    return client.put(
        f"/organizations/{organization.id}",
        json=body,
        headers=auth_headers(user),
    )


def test_an_organization_can_be_saved_back_as_the_api_returned_it(
    client, test_user, organization
):
    body = form_payload(client, test_user, organization)
    assert (
        body["phone"] is None
    )  # the premise: never-filled fields come back null
    body["city"] = "Aarhus"  # the user changes one field

    res = put(client, test_user, organization, body)

    assert res.status_code == 200, res.get_json()
    assert stored(organization).city == "Aarhus"
    assert stored(organization).phone is None


@pytest.mark.parametrize("field", OPTIONAL_FIELDS)
def test_update_accepts_null_for_an_optional_field_and_clears_it(
    client, db_session, test_user, organization, field
):
    setattr(organization, field, "something")
    db_session.commit()
    body = form_payload(client, test_user, organization)
    body[field] = None

    res = put(client, test_user, organization, body)

    assert res.status_code == 200, res.get_json()
    assert getattr(stored(organization), field) is None


@pytest.mark.parametrize("field", OPTIONAL_FIELDS)
def test_create_accepts_null_for_an_optional_field(
    client, test_user, country, field
):
    res = client.post(
        "/organizations",
        json={
            "name": "Brand New ApS",
            "slug": "brand-new-aps",
            "email": "new@example.com",
            "country_id": country.id,
            field: None,
        },
        headers=auth_headers(test_user),
    )

    assert res.status_code == 201, res.get_json()


@pytest.mark.parametrize("field", ["name", "email", "country_id"])
def test_required_fields_still_reject_null(
    client, test_user, organization, field
):
    body = form_payload(client, test_user, organization)
    body[field] = None

    res = put(client, test_user, organization, body)

    assert res.status_code == 422
    assert field in res.get_json()["errors"]
