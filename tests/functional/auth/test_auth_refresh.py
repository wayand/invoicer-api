from flask.testing import FlaskClient


def test_auth_token_refresh(client: FlaskClient, tokens):
    refresh_token = tokens.get('refreshToken')
    assert isinstance(refresh_token, str)
    res = client.post(
        "/auth/refresh-token",
        headers={"Authorization": f"Bearer {refresh_token}"}
    )
    assert res.status_code == 200
    data = res.get_json()
    assert "accessToken" in data
    assert isinstance(data["accessToken"], str)

def test_refresh_token_missing_header(client: FlaskClient):
    res = client.post("/auth/refresh-token")
    assert res.status_code == 401
    assert "Missing" in res.get_data(as_text=True)

def test_refresh_token_using_access_token(client: FlaskClient, tokens):
    access_token = tokens.get("accessToken")
    assert isinstance(access_token, str)
    res = client.post(
        "/auth/refresh-token",
        headers={"Authorization": f"Bearer {access_token}"}
    )

    # Flask-JWT-Extended returns 422 when the token is not a refresh token
    assert res.status_code == 422
    body = res.get_json()
    assert body is not None
    assert "token" in body["msg"].lower()

def test_refresh_token_contains_correct_claims(client: FlaskClient, tokens, test_user):
    refresh_token = tokens.get("refreshToken")
    assert isinstance(refresh_token, str)
    res = client.post(
        "/auth/refresh-token",
        headers={"Authorization": f"Bearer {refresh_token}"}
    )

    assert res.status_code == 200
    new_access_token = res.get_json()["accessToken"]

    # decode token using your jwt_manager
    from flask_jwt_extended import decode_token
    decoded = decode_token(new_access_token)

    assert decoded["sub"] == test_user.email
    assert decoded["email"] == test_user.email
    assert decoded["organizationId"] == test_user.organization_id
    assert decoded["isTwoFactorAuth"] is True
    assert decoded["twoFactorAuthType"] == test_user.two_factor_auth_type
