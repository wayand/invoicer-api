from flask.testing import FlaskClient

from app.models.user import User


def test_auth_qrcode_success(
    client: FlaskClient, test_user, tokens, db_session
):
    assert test_user.otp_secret_temp == ""

    access_token = tokens.get("accessToken")
    assert isinstance(access_token, str)

    res = client.get(
        "/auth/qrcode", headers={"Authorization": f"Bearer {access_token}"}
    )
    assert res.status_code == 200
    assert res.content_type == "image/svg+xml"
    assert b"<svg" in res.data

    # Reload user from DB to confirm otp_secret_temp was written
    updated = db_session.get(User, (test_user.organization_id, test_user.email))
    assert updated.otp_secret_temp != ""
    assert len(updated.otp_secret_temp) > 10


def test_qrcode_unauthorized(client, db_session):
    res = client.get("/auth/qrcode")
    assert res.status_code == 401
