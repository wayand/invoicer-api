"""
Sessions end when they should: logout revokes both tokens, and changing or
resetting a password ends every other session, refresh tokens included.
"""

from datetime import UTC, datetime, timedelta

import pytest
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    decode_token,
)

from app.models.base import db
from app.models.revoked_token import RevokedToken
from app.models.user import User

PASSWORD = "password123"
NEW_PASSWORD = "brand-new-pass-1"


def bearer(token) -> dict:
    return {"Authorization": f"Bearer {token}"}


def device_session(user: User) -> dict:
    """Another logged-in device: tokens carrying the user's current version."""
    claims = {"tv": user.token_version}
    return {
        "accessToken": create_access_token(
            identity=user.email, additional_claims=claims
        ),
        "refreshToken": create_refresh_token(
            identity=user.email, additional_claims=claims
        ),
    }


def whoami(client, access_token):
    return client.get("/auth/user", headers=bearer(access_token))


def refresh(client, refresh_token):
    return client.post("/auth/refresh-token", headers=bearer(refresh_token))


def logout(client, access_token, refresh_token=None):
    body = {} if refresh_token is None else {"refresh_token": refresh_token}
    return client.post("/auth/logout", json=body, headers=bearer(access_token))


def change_password(client, access_token, new_password=NEW_PASSWORD):
    return client.post(
        "/auth/change-password",
        json={"password": PASSWORD, "new_password": new_password},
        headers=bearer(access_token),
    )


def naive_utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@pytest.fixture
def other_user(db_session, organization) -> User:
    user = User(
        organization_id=organization.id,
        password_plaintext=PASSWORD,
        name="other user",
        email="other@example.com",
        otp_secret=User.generate_otp_secret(),
    )
    db_session.add(user)
    db_session.commit()
    return user


# ------------------------------------------------------------ token claim


def test_login_tokens_carry_the_users_token_version(
    client, db_session, test_user, tokens
):
    assert decode_token(tokens["accessToken"])["tv"] == 0
    assert decode_token(tokens["refreshToken"])["tv"] == 0


def test_refreshed_access_token_carries_the_token_version(
    client, test_user, tokens
):
    res = refresh(client, tokens["refreshToken"])

    assert decode_token(res.get_json()["accessToken"])["tv"] == 0


def test_tokens_without_the_claim_still_work(client, test_user):
    """Sessions that exist when this is deployed have no claim: version 0."""
    old_access = create_access_token(identity=test_user.email)
    old_refresh = create_refresh_token(identity=test_user.email)

    assert whoami(client, old_access).status_code == 200
    assert refresh(client, old_refresh).status_code == 200


# ----------------------------------------------------------------- logout


def test_logout_revokes_the_access_and_the_refresh_token(
    client, test_user, tokens
):
    res = logout(client, tokens["accessToken"], tokens["refreshToken"])

    assert res.status_code == 200
    assert whoami(client, tokens["accessToken"]).status_code == 401
    assert refresh(client, tokens["refreshToken"]).status_code == 401


def test_logout_without_a_refresh_token_still_revokes_the_access_token(
    client, test_user, tokens
):
    res = logout(client, tokens["accessToken"])

    assert res.status_code == 200
    assert whoami(client, tokens["accessToken"]).status_code == 401
    assert refresh(client, tokens["refreshToken"]).status_code == 200


def test_logout_keeps_the_users_other_sessions(client, test_user, tokens):
    other_device = device_session(test_user)

    logout(client, tokens["accessToken"], tokens["refreshToken"])

    assert whoami(client, other_device["accessToken"]).status_code == 200
    assert refresh(client, other_device["refreshToken"]).status_code == 200


def test_logout_requires_authentication(client):
    assert client.post("/auth/logout", json={}).status_code == 401


def test_logout_cannot_revoke_another_users_refresh_token(
    client, test_user, other_user
):
    mine = device_session(test_user)
    theirs = device_session(other_user)

    res = logout(client, mine["accessToken"], theirs["refreshToken"])

    assert res.status_code == 400
    assert refresh(client, theirs["refreshToken"]).status_code == 200
    assert whoami(client, mine["accessToken"]).status_code == 200


@pytest.mark.parametrize("bad", ["not-a-token", 12345, ["a"], {"a": 1}])
def test_logout_rejects_a_refresh_token_that_is_not_one(
    client, test_user, tokens, bad
):
    res = logout(client, tokens["accessToken"], bad)

    assert res.status_code == 400
    assert whoami(client, tokens["accessToken"]).status_code == 200


def test_logout_rejects_an_access_token_in_place_of_the_refresh_token(
    client, test_user, tokens
):
    res = logout(client, tokens["accessToken"], tokens["accessToken"])

    assert res.status_code == 400
    assert whoami(client, tokens["accessToken"]).status_code == 200


def test_logout_accepts_a_refresh_token_that_is_already_revoked(
    client, test_user, tokens
):
    revoked = client.post(
        "/auth/revoke-refresh-token", headers=bearer(tokens["refreshToken"])
    )
    assert revoked.status_code == 200

    res = logout(client, tokens["accessToken"], tokens["refreshToken"])

    assert res.status_code == 200
    assert whoami(client, tokens["accessToken"]).status_code == 401


# ------------------------------------------------------ revoked-token list


def test_revoked_tokens_remember_when_they_expire(client, test_user, tokens):
    expected = datetime.fromtimestamp(
        decode_token(tokens["accessToken"])["exp"], UTC
    ).replace(tzinfo=None)

    client.post(
        "/auth/revoke-access-token", headers=bearer(tokens["accessToken"])
    )

    row = RevokedToken.query.filter_by(
        jti=decode_token(tokens["accessToken"])["jti"]
    ).one()
    assert row.expires_at == expected


def test_a_token_cannot_be_listed_as_revoked_twice(db_session):
    db_session.add(RevokedToken(jti="same", expires_at=naive_utc_now()))
    db_session.commit()
    db_session.add(RevokedToken(jti="same", expires_at=naive_utc_now()))

    with pytest.raises(Exception, match="unique|duplicate"):
        db_session.commit()
    db_session.rollback()


def test_logout_purges_revoked_tokens_that_have_expired(
    client, db_session, test_user, tokens
):
    now = naive_utc_now()
    db_session.add_all(
        [
            RevokedToken(jti="expired", expires_at=now - timedelta(minutes=1)),
            RevokedToken(jti="still-valid", expires_at=now + timedelta(days=1)),
        ]
    )
    db_session.commit()

    logout(client, tokens["accessToken"], tokens["refreshToken"])

    remaining = {row.jti for row in RevokedToken.query.all()}
    assert "expired" not in remaining
    assert "still-valid" in remaining
    assert decode_token(tokens["accessToken"])["jti"] in remaining


# --------------------------------------------------------- password change


def test_changing_the_password_ends_the_users_other_sessions(
    client, db_session, test_user, tokens
):
    other_device = device_session(test_user)

    res = change_password(client, tokens["accessToken"])

    assert res.status_code == 200
    assert whoami(client, other_device["accessToken"]).status_code == 401
    assert refresh(client, other_device["refreshToken"]).status_code == 401
    db_session.refresh(test_user)
    assert test_user.token_version == 1


def test_changing_the_password_hands_this_device_a_new_session(
    client, test_user, tokens
):
    res = change_password(client, tokens["accessToken"])
    body = res.get_json()

    assert whoami(client, body["accessToken"]).status_code == 200
    renewed = refresh(client, body["refreshToken"])
    assert renewed.status_code == 200
    assert whoami(client, renewed.get_json()["accessToken"]).status_code == 200
    assert decode_token(body["accessToken"])["tv"] == 1
    assert decode_token(body["refreshToken"])["tv"] == 1


def test_the_old_tokens_of_this_device_stop_working_too(
    client, test_user, tokens
):
    change_password(client, tokens["accessToken"])

    assert whoami(client, tokens["accessToken"]).status_code == 401
    assert refresh(client, tokens["refreshToken"]).status_code == 401


def test_a_refreshed_token_cannot_outlive_a_password_change(
    client, test_user, tokens
):
    stale_access = refresh(client, tokens["refreshToken"]).get_json()[
        "accessToken"
    ]

    change_password(client, tokens["accessToken"])

    assert whoami(client, stale_access).status_code == 401


def test_wrong_old_password_leaves_every_session_alone(
    client, db_session, test_user, tokens
):
    res = client.post(
        "/auth/change-password",
        json={"password": "wrong-password", "new_password": NEW_PASSWORD},
        headers=bearer(tokens["accessToken"]),
    )

    assert res.status_code == 422
    assert "accessToken" not in res.get_json()
    assert whoami(client, tokens["accessToken"]).status_code == 200
    assert refresh(client, tokens["refreshToken"]).status_code == 200
    db_session.refresh(test_user)
    assert test_user.token_version == 0


def test_changing_the_password_leaves_other_users_sessions_alone(
    client, test_user, other_user, tokens
):
    theirs = device_session(other_user)

    change_password(client, tokens["accessToken"])

    assert whoami(client, theirs["accessToken"]).status_code == 200
    assert refresh(client, theirs["refreshToken"]).status_code == 200


# ---------------------------------------------------------- password reset


def test_resetting_the_password_ends_every_session(
    client, db_session, test_user, tokens
):
    other_device = device_session(test_user)

    res = client.post(
        "/auth/reset-password",
        json={
            "reset_code": test_user.get_reset_password_token(),
            "new_password": NEW_PASSWORD,
        },
    )

    assert res.status_code == 200
    for session in (tokens, other_device):
        assert whoami(client, session["accessToken"]).status_code == 401
        assert refresh(client, session["refreshToken"]).status_code == 401
    db_session.refresh(test_user)
    assert test_user.token_version == 1


def test_a_failed_reset_leaves_sessions_alone(client, test_user, tokens):
    res = client.post(
        "/auth/reset-password",
        json={"reset_code": "not-a-real-token", "new_password": NEW_PASSWORD},
    )

    assert res.status_code == 400
    assert whoami(client, tokens["accessToken"]).status_code == 200


def test_tokens_issued_after_a_password_change_carry_the_new_version(
    client, db_session, test_user
):
    test_user.token_version = 3
    db.session.commit()

    assert (
        whoami(
            client, create_access_token(identity=test_user.email)
        ).status_code
        == 401
    )
    assert (
        whoami(client, device_session(test_user)["accessToken"]).status_code
        == 200
    )
