from flask.testing import FlaskClient


def test_auth_user(client: FlaskClient, tokens):
    res = client.get(
        "/auth/user",
        headers={"Authorization": f"Bearer {tokens['accessToken']}"}
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["email"] == "test@example.com"
