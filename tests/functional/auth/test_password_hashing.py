"""
Passwords are hashed with argon2id. Accounts still holding an old PBKDF2
hash keep working and are moved to argon2id the next time they log in.
"""

import re

import pytest
from argon2 import PasswordHasher, Type
from flask_jwt_extended import create_access_token
from passlib.hash import pbkdf2_sha256

from app import mail
from app.models import user as user_module
from app.models.user import User

PASSWORD = "password123"
NEW_PASSWORD = "brand-new-pass-1"


def legacy_hash(password=PASSWORD) -> str:
    return pbkdf2_sha256.hash(password)


def bearer(user) -> dict:
    token = create_access_token(
        identity=user.email, additional_claims={"tv": user.token_version}
    )
    return {"Authorization": f"Bearer {token}"}


def login(client, email, password=PASSWORD):
    """Both login steps; returns the second response."""
    with mail.record_messages() as outbox:
        first = client.post(
            "/auth/token", json={"email": email, "password": password}
        )
    if first.status_code != 206:
        return first
    code = re.search(r"\b(\d{6})\b", outbox[-1].body).group(1)
    return client.post(
        "/auth/token",
        json={"email": email, "password": password, "otp_2fa": code},
    )


@pytest.fixture
def legacy_user(db_session, test_user) -> User:
    """test_user as an account created before argon2: a PBKDF2 hash."""
    test_user.password_hash = legacy_hash()
    db_session.commit()
    return test_user


# ------------------------------------------------------------ new hashes


def test_new_hashes_are_argon2id_with_the_rfc_9106_low_memory_profile():
    hashed = User.generate_hash(PASSWORD)

    assert hashed.startswith("$argon2id$")
    assert "m=65536,t=3,p=4" in hashed


def test_a_new_user_gets_an_argon2id_hash(test_user):
    assert test_user.password_hash.startswith("$argon2id$")


def test_a_hash_fits_the_password_column():
    longest = User.generate_hash("x" * 1000)

    assert len(longest) <= User.password_hash.type.length


def test_the_dummy_hash_for_unknown_emails_is_argon2id_too():
    """An unknown address must cost the same check as a known one."""
    assert user_module._DUMMY_PASSWORD_HASH.startswith("$argon2id$")


# ------------------------------------------------------------ verifying


@pytest.mark.parametrize(
    "make_hash", [User.generate_hash, lambda pw: legacy_hash(pw)]
)
def test_verify_hash_accepts_both_kinds_of_hash(make_hash):
    hashed = make_hash(PASSWORD)

    assert User.verify_hash(PASSWORD, hashed)
    assert not User.verify_hash("wrong-password", hashed)


def test_a_legacy_account_can_still_log_in(client, legacy_user):
    res = login(client, legacy_user.email)

    assert res.status_code == 200
    assert "accessToken" in res.get_json()


@pytest.mark.parametrize(
    "path,method",
    [("/auth/backup-codes", "post"), ("/auth/totp-setup", "delete")],
)
def test_password_checks_elsewhere_accept_a_legacy_hash(
    client, legacy_user, path, method
):
    ok = getattr(client, method)(
        path, json={"password": PASSWORD}, headers=bearer(legacy_user)
    )
    wrong = getattr(client, method)(
        path, json={"password": "wrong-password"}, headers=bearer(legacy_user)
    )

    assert ok.status_code == 200
    assert wrong.status_code == 422


# ----------------------------------------------------- upgrade at login


def test_logging_in_upgrades_a_legacy_hash_to_argon2id(
    client, db_session, legacy_user
):
    assert login(client, legacy_user.email).status_code == 200

    db_session.refresh(legacy_user)
    assert legacy_user.password_hash.startswith("$argon2id$")
    assert User.verify_hash(PASSWORD, legacy_user.password_hash)


def test_the_upgraded_account_keeps_logging_in(client, db_session, legacy_user):
    login(client, legacy_user.email)

    assert login(client, legacy_user.email).status_code == 200


def test_an_argon2_hash_is_not_rewritten_on_every_login(
    client, db_session, test_user
):
    before = test_user.password_hash

    assert login(client, test_user.email).status_code == 200

    db_session.refresh(test_user)
    assert test_user.password_hash == before


def test_an_argon2_hash_with_weaker_parameters_is_upgraded_too(
    client, db_session, test_user
):
    """Raising the parameters later moves accounts over the same way."""
    weak = PasswordHasher(
        type=Type.ID, time_cost=1, memory_cost=8 * 1024, parallelism=1
    ).hash(PASSWORD)
    test_user.password_hash = weak
    db_session.commit()

    assert login(client, test_user.email).status_code == 200

    db_session.refresh(test_user)
    assert test_user.password_hash != weak
    assert "m=65536,t=3,p=4" in test_user.password_hash


def test_a_wrong_password_does_not_upgrade_the_hash(
    client, db_session, legacy_user
):
    before = legacy_user.password_hash

    res = login(client, legacy_user.email, "wrong-password")

    assert res.status_code == 422
    db_session.refresh(legacy_user)
    assert legacy_user.password_hash == before


def test_the_upgrade_happens_at_the_password_step_of_login(
    client, db_session, legacy_user
):
    """Step one (password, then a code is sent) already proves the password."""
    client.post(
        "/auth/token",
        json={"email": legacy_user.email, "password": PASSWORD},
    )

    db_session.refresh(legacy_user)
    assert legacy_user.password_hash.startswith("$argon2id$")


def test_a_reset_link_issued_before_the_upgrade_stops_working(
    client, db_session, legacy_user
):
    """Reset links are bound to the password hash, so the upgrade ends them."""
    link_token = legacy_user.get_reset_password_token()
    login(client, legacy_user.email)

    res = client.post(
        "/auth/reset-password",
        json={"reset_code": link_token, "new_password": NEW_PASSWORD},
    )

    assert res.status_code == 400


# ------------------------------------------------ changing the password


def test_changing_the_password_stores_an_argon2id_hash(
    client, db_session, legacy_user
):
    res = client.post(
        "/auth/change-password",
        json={"password": PASSWORD, "new_password": NEW_PASSWORD},
        headers=bearer(legacy_user),
    )

    assert res.status_code == 200
    db_session.refresh(legacy_user)
    assert legacy_user.password_hash.startswith("$argon2id$")
    assert User.verify_hash(NEW_PASSWORD, legacy_user.password_hash)


def test_resetting_the_password_stores_an_argon2id_hash(
    client, db_session, legacy_user
):
    res = client.post(
        "/auth/reset-password",
        json={
            "reset_code": legacy_user.get_reset_password_token(),
            "new_password": NEW_PASSWORD,
        },
    )

    assert res.status_code == 200
    db_session.refresh(legacy_user)
    assert legacy_user.password_hash.startswith("$argon2id$")
    assert User.verify_hash(NEW_PASSWORD, legacy_user.password_hash)
