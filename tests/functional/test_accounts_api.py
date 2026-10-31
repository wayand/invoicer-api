"""The account routes: the fields the chart sets, and the unique number and
name of an account."""

import pytest
from flask_jwt_extended import create_access_token

from app.chart import apply_starter_chart
from app.models.account import Account
from app.models.organization import Organization
from app.models.user import User


def headers(user) -> dict:
    token = create_access_token(
        identity=user.email, additional_claims={"tv": user.token_version}
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def chart(db_session, organization):
    apply_starter_chart(organization)
    return {
        item.number: item
        for item in Account.query.filter_by(organization_id=organization.id)
    }


def as_app_sends(account_json: dict) -> dict:
    """The account as the app sends it back: what the API returned, without
    what the app strips (id, the nested objects and the timestamps)."""
    skip = {"id", "account_type", "account_group"}
    skip |= {"created_at", "updated_at", "standard_account", "system_role"}
    return {
        key: value for key, value in account_json.items() if key not in skip
    }


def test_an_account_is_returned_with_its_standard_account_and_role(
    client, test_user, chart
):
    res = client.get(f"/accounts/{chart[6480].id}", headers=headers(test_user))

    assert res.status_code == 200, res.get_json()
    assert res.get_json()["standard_account"] == 6480
    assert res.get_json()["system_role"] == "bank"


def test_the_list_has_them_too_and_an_account_without_them_has_null(
    client, db_session, test_user, chart
):
    chart[1210].standard_account = None
    db_session.commit()

    res = client.get("/accounts", headers=headers(test_user))

    by_number = {item["number"]: item for item in res.get_json()}
    assert by_number[7680]["system_role"] == "output_vat"
    assert by_number[1210]["standard_account"] is None
    assert by_number[1210]["system_role"] is None


def test_an_account_can_be_saved_as_the_app_sends_it(client, test_user, chart):
    sent = as_app_sends(
        client.get(
            f"/accounts/{chart[2450].id}", headers=headers(test_user)
        ).get_json()
    )
    sent["name"] = "Kontorartikler og papir"

    res = client.put(
        f"/accounts/{chart[2450].id}", json=sent, headers=headers(test_user)
    )

    assert res.status_code == 200, res.get_json()
    assert res.get_json()["name"] == "Kontorartikler og papir"
    assert res.get_json()["system_role"] is None


@pytest.mark.parametrize("field", ["standard_account", "system_role"])
def test_a_client_cannot_set_the_standard_account_or_role(
    client, test_user, chart, field
):
    sent = as_app_sends(
        client.get(
            f"/accounts/{chart[2450].id}", headers=headers(test_user)
        ).get_json()
    )
    sent[field] = 7680 if field == "standard_account" else "bank"

    res = client.put(
        f"/accounts/{chart[2450].id}", json=sent, headers=headers(test_user)
    )

    assert res.status_code == 422, res.get_json()
    assert field in res.get_json()["errors"]


def test_an_account_with_a_role_can_be_renamed_and_renumbered(
    client, test_user, chart
):
    sent = as_app_sends(
        client.get(
            f"/accounts/{chart[6480].id}", headers=headers(test_user)
        ).get_json()
    )
    sent.update(name="Driftskonto", number=6485)

    res = client.put(
        f"/accounts/{chart[6480].id}", json=sent, headers=headers(test_user)
    )

    assert res.status_code == 200, res.get_json()
    assert res.get_json()["system_role"] == "bank"
    assert res.get_json()["number"] == 6485


def test_an_account_cannot_take_a_number_that_is_used(client, test_user, chart):
    sent = as_app_sends(
        client.get(
            f"/accounts/{chart[2450].id}", headers=headers(test_user)
        ).get_json()
    )
    sent["number"] = 2410

    res = client.put(
        f"/accounts/{chart[2450].id}", json=sent, headers=headers(test_user)
    )

    assert res.status_code == 409
    assert res.get_json()["error"] == "Account number 2410 is already in use"


def test_an_account_cannot_take_a_name_that_is_used(client, test_user, chart):
    sent = as_app_sends(
        client.get(
            f"/accounts/{chart[2450].id}", headers=headers(test_user)
        ).get_json()
    )
    sent["name"] = chart[2410].name

    res = client.put(
        f"/accounts/{chart[2450].id}", json=sent, headers=headers(test_user)
    )

    assert res.status_code == 409
    assert "is already in use" in res.get_json()["error"]


def test_an_account_keeps_its_own_number_and_name_on_save(
    client, test_user, chart
):
    sent = as_app_sends(
        client.get(
            f"/accounts/{chart[2450].id}", headers=headers(test_user)
        ).get_json()
    )

    res = client.put(
        f"/accounts/{chart[2450].id}", json=sent, headers=headers(test_user)
    )

    assert res.status_code == 200, res.get_json()


def new_account(chart, **overrides) -> dict:
    existing = chart[2450]
    body = {
        "name": "Nyt udgiftskonto",
        "number": 2999,
        "account_type_id": existing.account_type_id,
        "account_group_id": existing.account_group_id,
    }
    body.update(overrides)
    return body


def test_an_account_can_be_created(client, test_user, chart):
    res = client.post(
        "/accounts", json=new_account(chart), headers=headers(test_user)
    )

    assert res.status_code == 201, res.get_json()
    assert res.get_json()["system_role"] is None
    assert res.get_json()["standard_account"] is None


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"number": 2450}, "Account number 2450 is already in use"),
        ({"name": "Kontorartikler"}, "is already in use"),
    ],
)
def test_an_account_cannot_be_created_with_a_used_number_or_name(
    client, test_user, chart, overrides, message
):
    res = client.post(
        "/accounts",
        json=new_account(chart, **overrides),
        headers=headers(test_user),
    )

    assert res.status_code == 409
    assert message in res.get_json()["error"]


def test_another_organization_can_use_the_same_number_and_name(
    client, db_session, country, chart
):
    other = Organization(
        name="Other ApS",
        slug="other-aps",
        country_id=country.id,
        email="other@example.com",
        logo="",
    )
    db_session.add(other)
    db_session.flush()
    other_user = User(
        organization_id=other.id,
        password_plaintext="password123",
        name="Other",
        email="other@example.com",
        otp_secret=User.generate_otp_secret(),
    )
    db_session.add(other_user)
    db_session.commit()
    apply_starter_chart(other)

    res = client.get("/accounts", headers=headers(other_user))

    numbers = [item["number"] for item in res.get_json()]
    assert 2450 in numbers
    assert len(numbers) == len(set(numbers))


def test_an_account_of_another_organization_is_not_found(
    client, db_session, country, chart
):
    other = Organization(
        name="Third ApS",
        slug="third-aps",
        country_id=country.id,
        email="third@example.com",
        logo="",
    )
    db_session.add(other)
    db_session.flush()
    other_user = User(
        organization_id=other.id,
        password_plaintext="password123",
        name="Third",
        email="third@example.com",
        otp_secret=User.generate_otp_secret(),
    )
    db_session.add(other_user)
    db_session.commit()

    res = client.put(
        f"/accounts/{chart[2450].id}",
        json=new_account(chart, number=2450),
        headers=headers(other_user),
    )

    assert res.status_code == 404
