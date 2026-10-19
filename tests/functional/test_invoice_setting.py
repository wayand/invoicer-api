"""
A reminder fee of 0 has to survive a round trip: saved as 0, it comes back as
0 (not null), so the form can load it and save it again.
"""

from decimal import Decimal

from flask_jwt_extended import create_access_token

from app.models.invoice_setting import InvoiceSetting


def auth_headers(user) -> dict:
    return {
        "Authorization": f"Bearer {create_access_token(identity=user.email)}"
    }


def settings_payload(invoice_setting, fee) -> dict:
    return {
        "template_id": "1",
        "invoice_no_mode": "manual",
        "next_invoice_no": 5,
        "default_account_id": invoice_setting.default_account_id,
        "default_deposit_account_id": invoice_setting.default_deposit_account_id,
        "default_reminder_fee": fee,
    }


def organization_fee(client, user, organization):
    res = client.get(
        f"/organizations/{organization.id}", headers=auth_headers(user)
    )
    assert res.status_code == 200
    return res.get_json()["invoice_setting"]["default_reminder_fee"]


def test_a_stored_fee_of_zero_is_returned_as_zero(
    client, test_user, organization, invoice_setting
):
    assert invoice_setting.default_reminder_fee == 0  # the fee is stored as 0

    fee = organization_fee(client, test_user, organization)

    assert fee == 0
    assert fee is not None


def test_saving_a_fee_of_zero_returns_it_as_zero(
    client, test_user, organization, invoice_setting
):
    res = client.put(
        "/invoice-setting",
        json=settings_payload(invoice_setting, 0),
        headers=auth_headers(test_user),
    )

    assert res.status_code == 200, res.get_json()
    assert res.get_json()["default_reminder_fee"] == 0
    assert res.get_json()["default_reminder_fee"] is not None
    assert organization_fee(client, test_user, organization) == 0


def test_a_fee_that_was_changed_to_zero_is_stored_as_zero(
    client, db_session, test_user, organization, invoice_setting
):
    invoice_setting.default_reminder_fee = Decimal("100")
    db_session.commit()

    res = client.put(
        "/invoice-setting",
        json=settings_payload(invoice_setting, 0),
        headers=auth_headers(test_user),
    )

    assert res.status_code == 200, res.get_json()
    stored = InvoiceSetting.query.filter_by(id=invoice_setting.id).one()
    assert stored.default_reminder_fee == 0
    assert organization_fee(client, test_user, organization) == 0


def test_another_fee_is_returned_as_saved(
    client, test_user, organization, invoice_setting
):
    res = client.put(
        "/invoice-setting",
        json=settings_payload(invoice_setting, 75.5),
        headers=auth_headers(test_user),
    )

    assert res.status_code == 200, res.get_json()
    assert res.get_json()["default_reminder_fee"] == 75.5
    assert organization_fee(client, test_user, organization) == 75.5
