"""
Passwords are hashed with argon2id, and a hash is moved to the current
parameters at the next login when they have changed. A hash in any other
format (such as the PBKDF2 ones this app used before argon2) never verifies:
the account is refused like a wrong password, and "forgot password" fixes it.
"""

import re

import pytest
from argon2 import PasswordHasher, Type
from flask_jwt_extended import create_access_token

from app import mail
from app.models import user as user_module
from app.models.user import User

PASSWORD = "password123"
NEW_PASSWORD = "brand-new-pass-1"
# A real PBKDF2 hash of PASSWORD, as written before argon2
OLD_FORMAT_HASH = "$pbkdf2-sha256$29000$KuVcay0lpPT.X6v1njMmhA$fg8K3nc489kPdp1SSDm5RGoBnkN14ga.8uEHPFOT9go"


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


def test_verify_hash_accepts_the_right_password_only():
    hashed = User.generate_hash(PASSWORD)

    assert User.verify_hash(PASSWORD, hashed)
    assert not User.verify_hash("wrong-password", hashed)


@pytest.mark.parametrize(
    "not_argon2", [OLD_FORMAT_HASH, "", "garbage", "$argon2id$truncated"]
)
def test_a_hash_that_is_not_argon2_never_verifies(not_argon2):
    assert User.verify_hash(PASSWORD, not_argon2) is False


def test_login_with_an_old_format_hash_is_refused_like_a_wrong_password(
    client, db_session, test_user
):
    test_user.password_hash = OLD_FORMAT_HASH
    db_session.commit()

    res = login(client, test_user.email)
    wrong = login(client, "nobody@example.com", "wrong-password")

    assert res.status_code == wrong.status_code == 422
    assert res.get_json() == wrong.get_json()


def test_forgot_password_recovers_an_account_with_an_old_format_hash(
    client, db_session, test_user
):
    test_user.password_hash = OLD_FORMAT_HASH
    db_session.commit()

    reset = client.post(
        "/auth/reset-password",
        json={
            "reset_code": test_user.get_reset_password_token(),
            "new_password": NEW_PASSWORD,
        },
    )

    assert reset.status_code == 200
    assert login(client, test_user.email, NEW_PASSWORD).status_code == 200


@pytest.mark.parametrize(
    "path,method",
    [("/auth/backup-codes", "post"), ("/auth/totp-setup", "delete")],
)
def test_password_checks_elsewhere_verify_argon2_hashes(
    client, test_user, path, method
):
    ok = getattr(client, method)(
        path, json={"password": PASSWORD}, headers=bearer(test_user)
    )
    wrong = getattr(client, method)(
        path, json={"password": "wrong-password"}, headers=bearer(test_user)
    )

    assert ok.status_code == 200
    assert wrong.status_code == 422


# ----------------------------------------------------- upgrade at login


def test_an_argon2_hash_is_not_rewritten_on_every_login(
    client, db_session, test_user
):
    before = test_user.password_hash

    assert login(client, test_user.email).status_code == 200

    db_session.refresh(test_user)
    assert test_user.password_hash == before


def test_an_argon2_hash_with_weaker_parameters_is_upgraded_at_login(
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
    assert login(client, test_user.email).status_code == 200


def test_a_wrong_password_does_not_upgrade_the_hash(
    client, db_session, test_user
):
    weak = PasswordHasher(
        type=Type.ID, time_cost=1, memory_cost=8 * 1024, parallelism=1
    ).hash(PASSWORD)
    test_user.password_hash = weak
    db_session.commit()

    res = login(client, test_user.email, "wrong-password")

    assert res.status_code == 422
    db_session.refresh(test_user)
    assert test_user.password_hash == weak


# ------------------------------------------------ changing the password


def test_changing_the_password_stores_an_argon2id_hash(
    client, db_session, test_user
):
    res = client.post(
        "/auth/change-password",
        json={"password": PASSWORD, "new_password": NEW_PASSWORD},
        headers=bearer(test_user),
    )

    assert res.status_code == 200
    db_session.refresh(test_user)
    assert test_user.password_hash.startswith("$argon2id$")
    assert User.verify_hash(NEW_PASSWORD, test_user.password_hash)


def test_resetting_the_password_stores_an_argon2id_hash(
    client, db_session, test_user
):
    res = client.post(
        "/auth/reset-password",
        json={
            "reset_code": test_user.get_reset_password_token(),
            "new_password": NEW_PASSWORD,
        },
    )

    assert res.status_code == 200
    db_session.refresh(test_user)
    assert test_user.password_hash.startswith("$argon2id$")
    assert User.verify_hash(NEW_PASSWORD, test_user.password_hash)
