
def test_new_user_with_fixture(new_user):
    """
    GIVEN a User model
    WHEN a new User is created
    THEN check the:
        organization_id,
        email, name, password_hash, owner,
        is_two_factor_auth, two_factor_auth_type
    """

    assert new_user.organization_id == 1
    assert new_user.email == 'demo_test@gmail.com'
    assert new_user.name == 'TheName'
    assert new_user.verify_hash('TheTextPassword', new_user.password_hash)
    assert new_user.owner is False
    assert new_user.is_two_factor_auth is True
    assert new_user.two_factor_auth_type == "2fa_otp_email"
