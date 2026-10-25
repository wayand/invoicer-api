"""
The server computes every amount on an invoice from the quantities and unit
prices (docs/money-rules.md). Amounts the client sends are not used.
"""

from datetime import date
from decimal import Decimal

import pytest
from flask_jwt_extended import create_access_token

from app.models.contact import Contact
from app.models.invoice import Invoice
from app.models.invoiceline import InvoiceLine
from app.models.product import Product
from app.models.tax_rate import TaxRate


def auth_headers(user) -> dict:
    return {
        "Authorization": f"Bearer {create_access_token(identity=user.email)}"
    }


@pytest.fixture
def contact(db_session, organization, country) -> Contact:
    contact = Contact(
        organization_id=organization.id,
        name="Client",
        email="client@example.com",
        country_id=country.id,
    )
    db_session.add(contact)
    db_session.commit()
    return contact


@pytest.fixture
def product(db_session, organization) -> Product:
    product = Product(
        organization_id=organization.id, name="Consulting", unit_price=100
    )
    db_session.add(product)
    db_session.commit()
    return product


def line(product, quantity, unit_price, **extra) -> dict:
    return {
        "product_id": product.id,
        "description": "Work",
        "quantity": quantity,
        "unit_price": unit_price,
        **extra,
    }


def body(organization, contact, lines, invoice_no="1001", **extra) -> dict:
    return {
        "organization_id": organization.id,
        "contact_id": contact.id,
        "invoice_no": invoice_no,
        "currency_id": "DKK",
        "state": "draft",
        "invoice_date": date(2026, 1, 1).isoformat(),
        "duedate": date(2026, 1, 15).isoformat(),
        "lines": lines,
        **extra,
    }


def create(client, user, organization, contact, lines, **extra):
    return client.post(
        f"/organizations/{organization.id}/invoices",
        json=body(organization, contact, lines, **extra),
        headers=auth_headers(user),
    )


def update(client, user, organization, invoice, contact, lines, **extra):
    return client.put(
        f"/organizations/{organization.id}/invoices/{invoice['id']}",
        json=body(
            organization,
            contact,
            lines,
            invoice_no=invoice["invoice_no"],
            **extra,
        ),
        headers=auth_headers(user),
    )


def totals(response_json) -> tuple:
    return (
        response_json["amount"],
        response_json["vat_amount"],
        response_json["gross_amount"],
    )


def saved_line(db_line) -> dict:
    """A line as the app sends it back: as returned, without the timestamps
    and the amount, which the server calculates."""
    return {
        key: value
        for key, value in db_line.items()
        if key not in ("created_at", "updated_at", "amount")
    }


def test_create_computes_the_amounts_from_the_lines(
    client, test_user, organization, contact, product, invoice_setting
):
    res = create(
        client,
        test_user,
        organization,
        contact,
        [line(product, 1, 100), line(product, 2, 100)],
    )

    assert res.status_code == 201, res.get_json()
    assert totals(res.get_json()) == (300.0, 75.0, 375.0)
    assert [item["amount"] for item in res.get_json()["lines"]] == [
        100.0,
        200.0,
    ]


def test_create_does_not_need_the_client_to_send_any_amounts(
    client, test_user, organization, contact, product, invoice_setting
):
    res = create(
        client, test_user, organization, contact, [line(product, 1, 100)]
    )

    assert res.status_code == 201, res.get_json()


@pytest.mark.parametrize(
    "field", ["amount", "vat_amount", "gross_amount", "excluding_vat"]
)
def test_create_rejects_an_invoice_field_the_server_calculates(
    client,
    db_session,
    test_user,
    organization,
    contact,
    product,
    invoice_setting,
    field,
):
    res = create(
        client,
        test_user,
        organization,
        contact,
        [line(product, 1, 100)],
        **{field: 1},
    )

    assert res.status_code == 422, res.get_json()
    assert field in res.get_json()["errors"]
    assert Invoice.query.count() == 0


def test_create_rejects_a_line_amount(
    client,
    db_session,
    test_user,
    organization,
    contact,
    product,
    invoice_setting,
):
    res = create(
        client,
        test_user,
        organization,
        contact,
        [line(product, 1, 100, amount=999)],
    )

    assert res.status_code == 422, res.get_json()
    assert Invoice.query.count() == 0


def test_a_line_is_rounded_half_up(
    client, test_user, organization, contact, product, invoice_setting
):
    res = create(
        client, test_user, organization, contact, [line(product, 3, 0.335)]
    )

    assert res.status_code == 201, res.get_json()
    assert res.get_json()["lines"][0]["amount"] == 1.01
    assert totals(res.get_json()) == (1.01, 0.25, 1.26)


def test_vat_is_rounded_half_up(
    client, test_user, organization, contact, product, invoice_setting
):
    res = create(
        client, test_user, organization, contact, [line(product, 1, 0.10)]
    )

    assert res.status_code == 201, res.get_json()
    assert totals(res.get_json()) == (0.10, 0.03, 0.13)


def test_each_line_is_rounded_before_the_lines_are_added(
    client, test_user, organization, contact, product, invoice_setting
):
    res = create(
        client,
        test_user,
        organization,
        contact,
        [line(product, 1, 0.005) for _ in range(10)],
    )

    assert res.status_code == 201, res.get_json()
    assert totals(res.get_json()) == (0.10, 0.03, 0.13)


def test_a_unit_price_keeps_its_three_decimals(
    client, test_user, organization, contact, product, invoice_setting
):
    res = create(
        client,
        test_user,
        organization,
        contact,
        [line(product, 1000, 0.125)],
    )

    assert res.status_code == 201, res.get_json()
    stored = InvoiceLine.query.filter_by(invoice_id=res.get_json()["id"]).one()
    assert stored.unit_price == Decimal("0.125")
    assert res.get_json()["lines"][0]["amount"] == 125.0


def test_a_negative_line_is_not_turned_into_null(
    client, test_user, organization, contact, product, invoice_setting
):
    res = create(
        client,
        test_user,
        organization,
        contact,
        [line(product, 1, 100), line(product, 1, -40)],
    )

    assert res.status_code == 201, res.get_json()
    assert [item["amount"] for item in res.get_json()["lines"]] == [
        100.0,
        -40.0,
    ]
    assert totals(res.get_json()) == (60.0, 15.0, 75.0)


def test_excluding_vat_is_not_returned(
    client, test_user, organization, contact, product, invoice_setting
):
    res = create(
        client, test_user, organization, contact, [line(product, 1, 100)]
    )

    assert res.status_code == 201, res.get_json()
    assert "excluding_vat" not in res.get_json()


def test_amounts_are_returned_as_json_numbers(
    client, test_user, organization, contact, product, invoice_setting
):
    res = create(
        client, test_user, organization, contact, [line(product, 1, 100)]
    )

    for value in totals(res.get_json()):
        assert isinstance(value, float)


def test_vat_uses_the_active_sales_tax_rate_of_the_organization(
    client,
    db_session,
    test_user,
    organization,
    contact,
    product,
    invoice_setting,
):
    rate = TaxRate.query.filter_by(organization_id=organization.id).one()
    rate.rate = Decimal("0.10")
    db_session.commit()

    res = create(
        client, test_user, organization, contact, [line(product, 1, 100)]
    )

    assert totals(res.get_json()) == (100.0, 10.0, 110.0)


def test_a_rate_of_zero_is_a_rate(
    client,
    db_session,
    test_user,
    organization,
    contact,
    product,
    invoice_setting,
):
    rate = TaxRate.query.filter_by(organization_id=organization.id).one()
    rate.rate = Decimal("0")
    db_session.commit()

    res = create(
        client, test_user, organization, contact, [line(product, 1, 100)]
    )

    assert res.status_code == 201, res.get_json()
    assert totals(res.get_json()) == (100.0, 0.0, 100.0)


def test_update_recomputes_the_amounts(
    client, test_user, organization, contact, product, invoice_setting
):
    invoice = create(
        client, test_user, organization, contact, [line(product, 1, 100)]
    ).get_json()

    res = update(
        client,
        test_user,
        organization,
        invoice,
        contact,
        [saved_line(invoice["lines"][0]) | {"quantity": 3}],
    )

    assert res.status_code == 200, res.get_json()
    assert totals(res.get_json()) == (300.0, 75.0, 375.0)
    assert res.get_json()["lines"][0]["amount"] == 300.0


@pytest.mark.parametrize(
    "field", ["amount", "vat_amount", "gross_amount", "excluding_vat"]
)
def test_update_rejects_an_invoice_field_the_server_calculates(
    client, test_user, organization, contact, product, invoice_setting, field
):
    invoice = create(
        client, test_user, organization, contact, [line(product, 1, 100)]
    ).get_json()

    res = update(
        client,
        test_user,
        organization,
        invoice,
        contact,
        [saved_line(invoice["lines"][0]) | {"quantity": 3}],
        **{field: 1},
    )

    assert res.status_code == 422, res.get_json()
    assert totals(
        client.get(
            f"/invoices/{invoice['id']}", headers=auth_headers(test_user)
        ).get_json()
    ) == (100.0, 25.0, 125.0)


def test_update_rejects_a_line_amount(
    client, test_user, organization, contact, product, invoice_setting
):
    invoice = create(
        client, test_user, organization, contact, [line(product, 1, 100)]
    ).get_json()

    res = update(
        client,
        test_user,
        organization,
        invoice,
        contact,
        [saved_line(invoice["lines"][0]) | {"quantity": 3, "amount": 999}],
    )

    assert res.status_code == 422, res.get_json()


def test_update_adds_up_exactly_the_lines_that_are_saved(
    client, test_user, organization, contact, product, invoice_setting
):
    invoice = create(
        client,
        test_user,
        organization,
        contact,
        [line(product, 1, 100), line(product, 1, 50)],
    ).get_json()
    kept = saved_line(invoice["lines"][0])  # the second line is removed

    res = update(
        client,
        test_user,
        organization,
        invoice,
        contact,
        [kept, line(product, 2, 10)],  # and a new one is added
    )

    assert res.status_code == 200, res.get_json()
    assert totals(res.get_json()) == (120.0, 30.0, 150.0)
    stored = Invoice.query.filter_by(id=invoice["id"]).one()
    assert sorted(item.amount for item in stored.lines) == [
        Decimal("20.00"),
        Decimal("100.00"),
    ]


def test_an_amount_too_large_to_store_is_refused_and_nothing_is_saved(
    client, test_user, organization, contact, product, invoice_setting
):
    res = create(
        client,
        test_user,
        organization,
        contact,
        [line(product, 99999999999, 99999999999)],
    )

    assert res.status_code == 422
    assert "too large" in res.get_json()["error"]
    assert Invoice.query.filter_by(organization_id=organization.id).count() == 0


def test_a_quantity_too_large_for_its_column_is_refused(
    client, test_user, organization, contact, product, invoice_setting
):
    res = create(
        client,
        test_user,
        organization,
        contact,
        [line(product, 1e12, 1)],
    )

    assert res.status_code == 422
    assert Invoice.query.filter_by(organization_id=organization.id).count() == 0


def test_create_needs_a_sales_tax_rate(
    client,
    db_session,
    test_user,
    organization,
    contact,
    product,
    invoice_setting,
):
    TaxRate.query.filter_by(organization_id=organization.id).delete()
    db_session.commit()

    res = create(
        client, test_user, organization, contact, [line(product, 1, 100)]
    )

    assert res.status_code == 409
    assert "sales tax rate" in res.get_json()["error"]
    assert Invoice.query.filter_by(organization_id=organization.id).count() == 0


def test_create_refuses_to_guess_between_two_sales_tax_rates(
    client,
    db_session,
    test_user,
    organization,
    contact,
    product,
    invoice_setting,
):
    db_session.add(
        TaxRate(
            organization_id=organization.id,
            name="Reduced",
            abbreviation="R",
            applies_to_sales=True,
            is_active=True,
            rate=Decimal("0.10"),
        )
    )
    db_session.commit()

    res = create(
        client, test_user, organization, contact, [line(product, 1, 100)]
    )

    assert res.status_code == 409


def test_an_inactive_sales_tax_rate_is_not_used(
    client,
    db_session,
    test_user,
    organization,
    contact,
    product,
    invoice_setting,
):
    db_session.add(
        TaxRate(
            organization_id=organization.id,
            name="Old",
            abbreviation="O",
            applies_to_sales=True,
            is_active=False,
            rate=Decimal("0.50"),
        )
    )
    db_session.commit()

    res = create(
        client, test_user, organization, contact, [line(product, 1, 100)]
    )

    assert res.status_code == 201, res.get_json()
    assert totals(res.get_json()) == (100.0, 25.0, 125.0)


def test_update_needs_a_sales_tax_rate(
    client,
    db_session,
    test_user,
    organization,
    contact,
    product,
    invoice_setting,
):
    invoice = create(
        client, test_user, organization, contact, [line(product, 1, 100)]
    ).get_json()
    TaxRate.query.filter_by(organization_id=organization.id).delete()
    db_session.commit()

    res = update(
        client,
        test_user,
        organization,
        invoice,
        contact,
        [saved_line(invoice["lines"][0])],
    )

    assert res.status_code == 409
