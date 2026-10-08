"""The password-reset email must link to the configured SITE_DOMAIN."""

import re

import pytest

from app import mail


def send_reset_mail(client, email):
    with mail.record_messages() as outbox:
        res = client.post("/auth/send-reset-mail", json={"email": email})
    assert res.status_code == 200
    return outbox[-1]


@pytest.mark.parametrize(
    "site_domain",
    ["https://invoicer.example.test", "https://invoicer.example.test/"],
)
def test_reset_email_links_to_the_configured_site(
    app, client, test_user, monkeypatch, site_domain
):
    monkeypatch.setitem(app.config, "SITE_DOMAIN", site_domain)
    message = send_reset_mail(client, test_user.email)

    for body in (message.body, message.html):
        assert "localhost" not in body
        assert "https://invoicer.example.test/reset-password?token=" in body
        assert "https://invoicer.example.test//" not in body


def test_the_emailed_link_actually_resets_the_password(
    app, client, test_user, monkeypatch
):
    monkeypatch.setitem(
        app.config, "SITE_DOMAIN", "https://invoicer.example.test"
    )
    message = send_reset_mail(client, test_user.email)

    token = re.search(r"reset-password\?token=([\w.\-]+)", message.html).group(
        1
    )
    res = client.post(
        "/auth/reset-password",
        json={"reset_code": token, "new_password": "brand-new-pass-1"},
    )
    assert res.status_code == 200


def test_reset_email_greets_by_name_and_is_signed_by_invoicer(
    client, test_user
):
    message = send_reset_mail(client, test_user.email)
    for body in (message.body, message.html):
        assert test_user.name in body
        assert "Invoicer" in body
        assert "Microblog" not in body
