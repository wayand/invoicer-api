"""
Organizations are created by the seed command, not through the API: the
frontend never creates one, and the route let any logged-in user create
organizations. It is gone, so nobody can.
"""

from flask_jwt_extended import create_access_token

from app.models.organization import Organization

BODY = {
    "name": "Unwanted Company ApS",
    "slug": "unwanted-company",
    "email": "unwanted@example.com",
}


def test_a_logged_in_user_cannot_create_an_organization(
    client, test_user, country
):
    token = create_access_token(
        identity=test_user.email,
        additional_claims={"tv": test_user.token_version},
    )
    before = Organization.query.count()

    res = client.post(
        "/organizations",
        json={**BODY, "country_id": country.id},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert res.status_code == 405
    assert Organization.query.count() == before
    assert Organization.query.filter_by(slug="unwanted-company").first() is None


def test_nobody_can_create_an_organization_without_logging_in_either(
    client, country
):
    res = client.post("/organizations", json={**BODY, "country_id": country.id})

    assert res.status_code == 405
    assert Organization.query.filter_by(slug="unwanted-company").first() is None


def test_listing_your_organizations_still_works(
    client, test_user, organization
):
    token = create_access_token(
        identity=test_user.email,
        additional_claims={"tv": test_user.token_version},
    )

    res = client.get(
        "/organizations", headers={"Authorization": f"Bearer {token}"}
    )

    assert res.status_code == 200
    assert [o["slug"] for o in res.get_json()] == [organization.slug]
