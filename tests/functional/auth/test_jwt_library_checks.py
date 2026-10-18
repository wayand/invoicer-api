"""
Checks the JWT library has to make before a token is trusted. Older PyJWT
(before 2.12 and 2.14) ignored an unknown critical header and extra characters
at the end of a signature; both are now rejected, and these tests keep it so.
"""

import jwt
import pytest
from flask_jwt_extended import create_access_token

from app.models.user import User


def reset_token_with_header(user, header) -> str:
    """A reset token signed with the real key, carrying an extra header."""
    return jwt.encode(
        {
            "purpose": "reset_password",
            "reset_password": user.id,
            "pwd": user._password_fingerprint(),
            "exp": 4102444800,  # the year 2100
        },
        User._reset_signing_key(),
        algorithm="HS256",
        headers=header,
    )


def test_a_reset_token_made_the_normal_way_is_accepted(test_user):
    token = test_user.get_reset_password_token()

    assert User.verify_reset_password_token(token).id == test_user.id


def test_a_reset_token_with_an_unknown_critical_header_is_refused(test_user):
    """RFC 7515 section 4.1.11: a verifier must reject a token whose `crit`
    header names an extension it does not understand."""
    token = reset_token_with_header(
        test_user, {"crit": ["x-extension"], "x-extension": 1}
    )

    assert User.verify_reset_password_token(token) is None


@pytest.mark.parametrize("junk", ["!!!!", "====", "\n", "  "])
def test_a_reset_token_with_junk_after_its_signature_is_refused(
    test_user, junk
):
    token = test_user.get_reset_password_token()

    assert User.verify_reset_password_token(token + junk) is None


@pytest.mark.parametrize("junk", ["!!!!", "$$"])
def test_an_access_token_with_junk_after_its_signature_is_refused(
    client, test_user, junk
):
    token = create_access_token(
        identity=test_user.email,
        additional_claims={"tv": test_user.token_version},
    )

    good = client.get(
        "/auth/user", headers={"Authorization": f"Bearer {token}"}
    )
    tampered = client.get(
        "/auth/user", headers={"Authorization": f"Bearer {token}{junk}"}
    )

    assert good.status_code == 200
    assert tampered.status_code in (401, 422)
