"""
Login, password-reset and password-verification hardening:
generic responses (no account enumeration), rate limits, and reset tokens
that are single-use and cannot be confused with access tokens.
"""

import pytest
from flask_jwt_extended import create_access_token

from app import mail
from app.models.user import User

PASSWORD = "password123"


def auth_headers(user: User) -> dict:
    return {
        "Authorization": f"Bearer {create_access_token(identity=user.email)}"
    }


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


def login(client, email, password=PASSWORD, **extra):
    return client.post(
        "/auth/token", json={"email": email, "password": password, **extra}
    )


# ------------------------------------------------------- generic responses


def test_login_unknown_email_and_wrong_password_look_identical(
    client, test_user
):
    unknown = login(client, "nobody@example.com", "whatever-123")
    wrong = login(client, test_user.email, "wrong-password")

    assert unknown.status_code == wrong.status_code == 422
    assert unknown.get_json() == wrong.get_json()
    assert "nobody@example.com" not in unknown.get_data(as_text=True)


def test_login_unknown_email_still_verifies_a_hash(
    client, test_user, monkeypatch
):
    """Same work for unknown and known emails, so timing doesn't leak."""
    calls = []
    original = User.verify_hash

    def spy(password, hash_):
        calls.append(hash_)
        return original(password, hash_)

    monkeypatch.setattr(User, "verify_hash", staticmethod(spy))
    login(client, "nobody@example.com", "whatever-123")
    assert len(calls) == 1


def test_login_second_step_does_not_echo_the_email(client, test_user):
    res = login(client, test_user.email)
    assert res.status_code == 206
    assert "ses" not in res.get_json()
    assert test_user.email not in res.get_data(as_text=True)


def test_resend_totp_email_does_not_echo_the_email(client, test_user):
    with client.session_transaction() as sess:
        sess["logging_in_user"] = test_user.email
    res = client.post("/auth/resend-totp-email")
    assert res.status_code == 200
    assert "ses" not in res.get_json()


def test_send_reset_mail_is_identical_for_known_and_unknown_email(
    client, test_user
):
    with mail.record_messages() as outbox:
        known = client.post(
            "/auth/send-reset-mail", json={"email": test_user.email}
        )
        unknown = client.post(
            "/auth/send-reset-mail", json={"email": "nobody@example.com"}
        )

    assert known.status_code == unknown.status_code == 200
    assert known.get_json() == unknown.get_json()
    assert [m.recipients for m in outbox] == [[test_user.email]]


# ----------------------------------------------------------- rate limiting


def test_login_locks_an_account_after_repeated_failures(
    client, test_user, other_user
):
    for _ in range(10):
        assert (
            login(client, test_user.email, "wrong-password").status_code == 422
        )

    locked = login(client, test_user.email)  # even the right password
    assert locked.status_code == 429
    assert locked.headers.get("Retry-After")
    assert locked.get_json() == {
        "error": "Too many attempts. Please try again later."
    }

    # other accounts are unaffected
    assert login(client, other_user.email, "wrong-password").status_code == 422


def test_login_lockout_is_the_same_for_unknown_emails(client):
    """Lockout state must not reveal whether an account exists."""
    for _ in range(10):
        assert (
            login(client, "nobody@example.com", "x-123456").status_code == 422
        )
    assert login(client, "nobody@example.com", "x-123456").status_code == 429


def test_ip_limit_cannot_be_dodged_with_a_spoofed_forwarded_header(client):
    """Different account every time, so only the per-IP limit can trigger.
    X-Forwarded-For is untrusted unless TRUSTED_PROXY_COUNT says otherwise."""
    for i in range(60):
        res = client.post(
            "/auth/token",
            json={"email": f"user{i}@example.com", "password": "x-1234567"},
            headers={"X-Forwarded-For": f"203.0.113.{i}"},
        )
        assert res.status_code == 422

    res = client.post(
        "/auth/token",
        json={"email": "one-more@example.com", "password": "x-1234567"},
        headers={"X-Forwarded-For": "198.51.100.200"},
    )
    assert res.status_code == 429


def test_send_reset_mail_is_limited_per_email(client, test_user):
    for email in (test_user.email, "nobody@example.com"):
        for _ in range(3):
            res = client.post("/auth/send-reset-mail", json={"email": email})
            assert res.status_code == 200
        res = client.post("/auth/send-reset-mail", json={"email": email})
        assert res.status_code == 429


def test_change_password_guessing_is_rate_limited(client, test_user):
    """A stolen access token must not become an unlimited password oracle."""
    body = {"password": "wrong-password", "new_password": "new-password-123"}
    for _ in range(5):
        res = client.post(
            "/auth/change-password", json=body, headers=auth_headers(test_user)
        )
        assert res.status_code == 422

    body["password"] = PASSWORD  # right password, but already locked
    res = client.post(
        "/auth/change-password", json=body, headers=auth_headers(test_user)
    )
    assert res.status_code == 429


def test_totp_delete_password_guessing_is_rate_limited(client, test_user):
    for _ in range(5):
        res = client.delete(
            "/auth/totp-setup",
            json={"password": "wrong-password"},
            headers=auth_headers(test_user),
        )
        assert res.status_code == 422
    res = client.delete(
        "/auth/totp-setup",
        json={"password": PASSWORD},
        headers=auth_headers(test_user),
    )
    assert res.status_code == 429


# ------------------------------------------------------- password reset


def reset(client, token, new_password="brand-new-pass-1"):
    return client.post(
        "/auth/reset-password",
        json={"reset_code": token, "new_password": new_password},
    )


def test_password_reset_happy_path(client, db_session, test_user):
    token = test_user.get_reset_password_token()
    res = reset(client, token)

    assert res.status_code == 200
    db_session.refresh(test_user)
    assert User.verify_hash("brand-new-pass-1", test_user.password_hash)
    assert not User.verify_hash(PASSWORD, test_user.password_hash)


def test_reset_token_is_single_use(client, test_user):
    token = test_user.get_reset_password_token()
    assert reset(client, token).status_code == 200

    again = reset(client, token, "another-new-pass-2")
    assert again.status_code == 400
    assert "resetCode" in again.get_json()["errors"]


def test_reset_token_dies_when_the_password_changes(
    client, db_session, test_user
):
    token = test_user.get_reset_password_token()
    test_user.password_hash = User.generate_hash("changed-in-the-meantime-1")
    db_session.commit()

    assert reset(client, token).status_code == 400


def test_garbage_reset_code_is_a_client_error_without_internals(client):
    res = reset(client, "not-a-real-token")
    assert res.status_code == 400
    body = res.get_json()
    assert set(body) == {"errors"}
    assert "resetCode" in body["errors"]
    assert "Traceback" not in res.get_data(as_text=True)


def test_access_token_is_not_accepted_as_a_reset_code(client, test_user):
    access = create_access_token(identity=test_user.email)
    assert reset(client, access).status_code == 400


# --------------------------------------------------------------- leakage


def test_server_errors_do_not_leak_exception_text(
    client, test_user, monkeypatch
):
    def boom(_password):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(User, "generate_hash", staticmethod(boom))
    res = client.post(
        "/auth/change-password",
        json={"password": PASSWORD, "new_password": "new-password-123"},
        headers=auth_headers(test_user),
    )
    assert res.status_code == 500
    assert b"secret internal detail" not in res.data
