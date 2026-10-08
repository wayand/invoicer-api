"""
Second factor at login: single-use email codes, replay-proof authenticator
codes with clock-drift tolerance, and backup codes (plus the recovery CLI).
"""

import base64
import os
import re
import time

import onetimepass
import pytest
from flask_jwt_extended import create_access_token

from app import cli, mail
from app.models.user import User

PASSWORD = "password123"
STEP = 30


# ---------------------------------------------------------------- helpers


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture
def clock(monkeypatch):
    """Freeze the time the User model sees, aligned to an authenticator step."""
    frozen = Clock((int(time.time()) // STEP) * STEP)
    monkeypatch.setattr("app.models.user._now_ts", frozen)
    return frozen


def auth_headers(user: User) -> dict:
    return {
        "Authorization": f"Bearer {create_access_token(identity=user.email)}"
    }


def login(client, email, **extra):
    return client.post(
        "/auth/token", json={"email": email, "password": PASSWORD, **extra}
    )


def email_code(client, user) -> str:
    """Login step 1 for an email-2FA account; returns the emailed code."""
    with mail.record_messages() as outbox:
        res = login(client, user.email)
    assert res.status_code == 206
    return re.search(r"\b(\d{6})\b", outbox[-1].body).group(1)


def totp(secret, now, offset=0) -> str:
    return f"{onetimepass.get_hotp(secret, int(now // STEP) + offset):06d}"


def wrong_code(real: str) -> str:
    return "000000" if real != "000000" else "111111"


@pytest.fixture
def mobile_user(db_session, test_user) -> User:
    test_user.otp_secret = User.generate_otp_secret()
    test_user.two_factor_auth_type = "2fa_mobile_app"
    db_session.commit()
    return test_user


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


def new_backup_codes(client, user) -> list:
    res = client.post(
        "/auth/backup-codes",
        json={"password": PASSWORD},
        headers=auth_headers(user),
    )
    assert res.status_code == 200
    return res.get_json()["codes"]


# ------------------------------------------------------------- email codes


def test_email_code_logs_in_once_and_is_then_dead(client, test_user):
    code = email_code(client, test_user)
    assert re.fullmatch(r"\d{6}", code)

    assert login(client, test_user.email, otp_2fa=code).status_code == 200
    assert login(client, test_user.email, otp_2fa=code).status_code == 422


@pytest.mark.parametrize("seconds, expected", [(599, 200), (601, 422)])
def test_email_code_expires_after_ten_minutes(
    client, test_user, clock, seconds, expected
):
    code = email_code(client, test_user)
    clock.advance(seconds)
    res = login(client, test_user.email, otp_2fa=code)
    assert res.status_code == expected


def test_email_code_is_stored_hashed(client, db_session, test_user):
    code = email_code(client, test_user)
    db_session.refresh(test_user)
    assert re.fullmatch(r"[0-9a-f]{64}", test_user.email_otp_hash)
    assert code not in test_user.email_otp_hash


def test_email_code_dies_after_five_wrong_attempts(client, test_user):
    code = email_code(client, test_user)
    for _ in range(5):
        res = login(client, test_user.email, otp_2fa=wrong_code(code))
        assert res.status_code == 422
    assert login(client, test_user.email, otp_2fa=code).status_code == 422


def test_four_wrong_attempts_do_not_burn_the_code(client, test_user):
    code = email_code(client, test_user)
    for _ in range(4):
        login(client, test_user.email, otp_2fa=wrong_code(code))
    assert login(client, test_user.email, otp_2fa=code).status_code == 200


def test_resend_invalidates_the_previous_code(client, test_user):
    first = email_code(client, test_user)  # also sets the login session
    with mail.record_messages() as outbox:
        res = client.post("/auth/resend-totp-email")
    assert res.status_code == 200
    second = re.search(r"\b(\d{6})\b", outbox[-1].body).group(1)
    if second == first:  # one-in-a-million collision; ask again
        with mail.record_messages() as outbox:
            client.post("/auth/resend-totp-email")
        second = re.search(r"\b(\d{6})\b", outbox[-1].body).group(1)
    if second == first:
        pytest.skip("random codes collided twice")

    assert login(client, test_user.email, otp_2fa=first).status_code == 422
    assert login(client, test_user.email, otp_2fa=second).status_code == 200


def test_email_code_email_states_the_real_lifetime(client, test_user):
    with mail.record_messages() as outbox:
        login(client, test_user.email)
    assert "10 minutes" in outbox[-1].html
    assert "30 minutes" not in outbox[-1].html


# ------------------------------------------------------ authenticator codes


def test_authenticator_code_works_once_and_cannot_be_replayed(
    client, mobile_user, clock
):
    code = totp(mobile_user.otp_secret, clock.now)
    assert login(client, mobile_user.email, otp_2fa=code).status_code == 200
    assert login(client, mobile_user.email, otp_2fa=code).status_code == 422


@pytest.mark.parametrize(
    "offset, expected", [(-1, 200), (0, 200), (1, 200), (-2, 422), (2, 422)]
)
def test_authenticator_tolerates_one_step_of_clock_drift(
    client, mobile_user, clock, offset, expected
):
    code = totp(mobile_user.otp_secret, clock.now, offset)
    res = login(client, mobile_user.email, otp_2fa=code)
    assert res.status_code == expected


def test_older_authenticator_code_is_rejected_after_a_newer_one(
    client, mobile_user, clock
):
    newer = totp(mobile_user.otp_secret, clock.now, +1)
    older = totp(mobile_user.otp_secret, clock.now, 0)
    assert login(client, mobile_user.email, otp_2fa=newer).status_code == 200
    assert login(client, mobile_user.email, otp_2fa=older).status_code == 422


def test_authenticator_account_gets_no_email_code(client, mobile_user):
    with mail.record_messages() as outbox:
        res = login(client, mobile_user.email)
    assert res.status_code == 206
    assert res.get_json()["twoFactorType"] == "2fa_mobile_app"
    assert outbox == []


def test_legacy_80_bit_authenticator_secrets_keep_working(
    client, db_session, mobile_user, clock
):
    """Existing users enrolled with the old 16-character secrets."""
    legacy = base64.b32encode(os.urandom(10)).decode()
    assert len(legacy) == 16
    mobile_user.otp_secret = legacy
    db_session.commit()

    code = totp(legacy, clock.now)
    assert login(client, mobile_user.email, otp_2fa=code).status_code == 200


def test_new_authenticator_secrets_are_160_bit():
    assert len(User.generate_otp_secret()) == 32


# ------------------------------------------------------------ backup codes


def test_backup_codes_need_the_password(client, test_user):
    res = client.post(
        "/auth/backup-codes",
        json={"password": "wrong-password"},
        headers=auth_headers(test_user),
    )
    assert res.status_code == 422


def test_backup_codes_need_a_logged_in_user(client):
    assert client.post("/auth/backup-codes", json={}).status_code == 401
    assert client.get("/auth/backup-codes").status_code == 401


def test_backup_codes_are_ten_unique_and_nicely_formatted(client, test_user):
    codes = new_backup_codes(client, test_user)
    assert len(codes) == len(set(codes)) == 10
    assert all(re.fullmatch(r"[A-Z2-9]{5}-[A-Z2-9]{5}", c) for c in codes)

    res = client.get("/auth/backup-codes", headers=auth_headers(test_user))
    assert res.get_json() == {"remaining": 10}


def test_backup_code_logs_in_once_and_is_reported(client, test_user):
    codes = new_backup_codes(client, test_user)

    with mail.record_messages() as outbox:
        assert (
            login(client, test_user.email, otp_2fa=codes[0]).status_code == 200
        )
    assert any("backup code" in m.subject.lower() for m in outbox)

    assert login(client, test_user.email, otp_2fa=codes[0]).status_code == 422
    res = client.get("/auth/backup-codes", headers=auth_headers(test_user))
    assert res.get_json() == {"remaining": 9}


def test_backup_code_works_for_authenticator_accounts(client, mobile_user):
    codes = new_backup_codes(client, mobile_user)
    res = login(client, mobile_user.email, otp_2fa=codes[3])
    assert res.status_code == 200


def test_backup_code_entry_is_forgiving(client, test_user):
    codes = new_backup_codes(client, test_user)
    typed = " " + codes[0].replace("-", "").lower() + " "
    assert login(client, test_user.email, otp_2fa=typed).status_code == 200


def test_regenerating_invalidates_the_old_codes(client, test_user):
    old = new_backup_codes(client, test_user)
    new = new_backup_codes(client, test_user)

    assert login(client, test_user.email, otp_2fa=old[0]).status_code == 422
    assert login(client, test_user.email, otp_2fa=new[0]).status_code == 200


def test_backup_codes_are_stored_hashed(client, db_session, test_user):
    from app.models.backup_code import BackupCode

    codes = new_backup_codes(client, test_user)
    stored = [row.code_hash for row in BackupCode.query.all()]
    assert len(stored) == 10
    assert all(re.fullmatch(r"[0-9a-f]{64}", h) for h in stored)
    raw = {c.replace("-", "") for c in codes}
    assert not raw & set(stored)


def test_one_users_backup_code_is_useless_for_another(
    client, test_user, other_user
):
    others = client.post(
        "/auth/backup-codes",
        json={"password": PASSWORD},
        headers=auth_headers(other_user),
    ).get_json()["codes"]
    assert login(client, test_user.email, otp_2fa=others[0]).status_code == 422


def test_backup_code_generation_guessing_is_rate_limited(client, test_user):
    for _ in range(5):
        res = client.post(
            "/auth/backup-codes",
            json={"password": "wrong-password"},
            headers=auth_headers(test_user),
        )
        assert res.status_code == 422
    res = client.post(
        "/auth/backup-codes",
        json={"password": PASSWORD},
        headers=auth_headers(test_user),
    )
    assert res.status_code == 429


# ----------------------------------------------------------- recovery CLI


def test_reset_2fa_cli_returns_the_account_to_email_codes(
    app, runner, db_session, mobile_user, client
):
    from app.models.backup_code import BackupCode

    cli.register_commands(app)
    old_secret = mobile_user.otp_secret
    new_backup_codes(client, mobile_user)

    result = runner.invoke(args=["user-reset-2fa", mobile_user.email])

    assert result.exit_code == 0, result.output
    db_session.refresh(mobile_user)
    assert mobile_user.two_factor_auth_type == "2fa_otp_email"
    assert mobile_user.otp_secret != old_secret
    assert mobile_user.totp_last_used_step is None
    assert BackupCode.query.count() == 0


def test_reset_2fa_cli_rejects_an_unknown_email(app, runner):
    cli.register_commands(app)
    result = runner.invoke(args=["user-reset-2fa", "nobody@example.com"])
    assert result.exit_code != 0
    assert "no user" in result.output.lower()
