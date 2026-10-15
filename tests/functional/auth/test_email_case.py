"""
An email address is one identity however it is typed: Test@Example.com and
test@example.com are the same account. Addresses are stored lowercase, the
database enforces it, and every lookup from user input normalizes.
"""

import re

import pytest
from flask_jwt_extended import create_access_token
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app import cli, mail
from app.models.organization import Organization
from app.models.user import User
from app.routes.auth_routes import generate_token

PASSWORD = "password123"
SPELLINGS = ["TEST@EXAMPLE.COM", "Test@Example.com", "  test@example.com  "]


def bearer(token) -> dict:
    return {"Authorization": f"Bearer {token}"}


def first_step(client, email, password=PASSWORD):
    return client.post(
        "/auth/token", json={"email": email, "password": password}
    )


def full_login(client, email):
    """Both login steps, with the email typed as given."""
    with mail.record_messages() as outbox:
        step_one = first_step(client, email)
    assert step_one.status_code == 206, step_one.get_data(as_text=True)
    code = re.search(r"\b(\d{6})\b", outbox[-1].body).group(1)
    return client.post(
        "/auth/token",
        json={"email": email, "password": PASSWORD, "otp_2fa": code},
    )


# ------------------------------------------------------------------ login


@pytest.mark.parametrize("email", SPELLINGS)
def test_login_works_whatever_the_case_of_the_email(client, test_user, email):
    res = full_login(client, email)

    assert res.status_code == 200
    assert "accessToken" in res.get_json()


@pytest.mark.parametrize("email", SPELLINGS)
def test_the_login_code_is_sent_to_the_stored_address(client, test_user, email):
    with mail.record_messages() as outbox:
        first_step(client, email)

    assert [m.recipients for m in outbox] == [["test@example.com"]]


def test_a_wrong_password_looks_the_same_in_any_case(client, test_user):
    lower = first_step(client, "test@example.com", "wrong-password")
    upper = first_step(client, "TEST@EXAMPLE.COM", "wrong-password")
    unknown = first_step(client, "nobody@example.com", "wrong-password")

    assert lower.status_code == upper.status_code == unknown.status_code == 422
    assert lower.get_json() == upper.get_json() == unknown.get_json()


# --------------------------------------------------------- forgot password


@pytest.mark.parametrize("email", SPELLINGS)
def test_forgot_password_sends_the_email_whatever_the_case(
    client, test_user, email
):
    with mail.record_messages() as outbox:
        res = client.post("/auth/send-reset-mail", json={"email": email})

    assert res.status_code == 200
    assert [m.recipients for m in outbox] == [["test@example.com"]]


# ----------------------------------------------------------- stored value


@pytest.mark.parametrize("email", SPELLINGS + ["MiXeD@Example.COM"])
def test_a_new_user_gets_a_lowercase_trimmed_email(organization, email):
    user = User(
        organization_id=organization.id,
        email=email,
        name="N",
        password_plaintext=PASSWORD,
    )

    assert user.email == email.strip().lower()


def test_assigning_an_email_later_normalizes_it_too(test_user):
    test_user.email = "  New.Address@Example.COM "

    assert test_user.email == "new.address@example.com"


def test_two_users_cannot_differ_only_by_case(db_session, country, test_user):
    other = Organization(
        name="Other ApS",
        slug="other-aps",
        country_id=country.id,
        email="other@example.com",
        logo="",
    )
    db_session.add(other)
    db_session.commit()
    db_session.add(
        User(
            organization_id=other.id,
            email="TEST@example.com",
            name="Twin",
            password_plaintext=PASSWORD,
            otp_secret=User.generate_otp_secret(),
        )
    )

    with pytest.raises(IntegrityError, match="uq_users_email"):
        db_session.commit()
    db_session.rollback()


def test_the_database_rejects_a_mixed_case_email_whatever_wrote_it(
    db_session, test_user
):
    with pytest.raises(IntegrityError, match="ck_users_email_lowercase"):
        db_session.execute(
            text("UPDATE users SET email = 'Test@Example.com' WHERE id = :id"),
            {"id": test_user.id},
        )
    db_session.rollback()


# ----------------------------------------------------------------- lookup


def test_find_by_email_ignores_case_and_padding(test_user):
    assert User.find_by_email("  TEST@Example.COM ").id == test_user.id


@pytest.mark.parametrize("bad", [None, "", "   ", 42, ["a"], {"a": 1}])
def test_find_by_email_finds_nobody_for_a_value_that_is_not_an_email(
    test_user, bad
):
    assert User.find_by_email(bad) is None


# ------------------------------------------------- sessions and old links


def test_a_token_issued_with_a_mixed_case_address_still_works(
    client, test_user
):
    """Sessions from before addresses were normalized carry whatever case the
    user was stored with."""
    token = create_access_token(
        identity="Test@Example.COM", additional_claims={"tv": 0}
    )

    res = client.get("/auth/user", headers=bearer(token))

    assert res.status_code == 200
    assert res.get_json()["email"] == "test@example.com"


def test_a_confirm_email_link_made_with_a_mixed_case_address_works(
    client, db_session, test_user
):
    link_token = generate_token("Test@Example.com")
    access = create_access_token(
        identity=test_user.email, additional_claims={"tv": 0}
    )

    res = client.post(
        f"/auth/confirm-email/{link_token}", headers=bearer(access)
    )

    assert res.status_code == 200
    db_session.refresh(test_user)
    assert test_user.email_is_confirmed is True


def test_a_confirm_email_link_for_someone_else_is_still_refused(
    client, db_session, test_user
):
    link_token = generate_token("someone.else@example.com")
    access = create_access_token(
        identity=test_user.email, additional_claims={"tv": 0}
    )

    res = client.post(
        f"/auth/confirm-email/{link_token}", headers=bearer(access)
    )

    assert res.status_code == 400
    db_session.refresh(test_user)
    assert test_user.email_is_confirmed is False


# -------------------------------------------------------------------- CLI


def test_the_recovery_command_finds_the_user_in_any_case(
    app, runner, test_user
):
    cli.register_commands(app)

    result = runner.invoke(args=["user-reset-2fa", "TEST@Example.com"])

    assert result.exit_code == 0, result.output
