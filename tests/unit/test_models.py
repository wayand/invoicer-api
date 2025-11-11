from app.models import User

def test_new_user():
    """
    Given a User model
    When a new User is created
    Then check the:
        organization_id,
        email, name, password_hash, owner,
        is_two_factor_auth, two_factor_auth_type
    """

    user = User(
        1,
        'demo_test@gmail.com',
        'TheName',
        'TheTextPassword'
    )

    assert user.organization_id == 1
    assert user.email == 'demo_test@gmail.com'
    assert user.name == 'TheName'
    assert user.verify_hash('TheTextPassword', user.password_hash)
    assert user.owner is False
    assert user.is_two_factor_auth is False
    assert user.two_factor_auth_type == "2fa_otp_email"
