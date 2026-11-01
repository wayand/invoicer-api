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
        "vat_code": "S01",
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


# --- the VAT code of every line --------------------------------------------


def vat_of(response_json) -> list:
    return [
        (item["code"], item["rate"], item["base"], item["vat"])
        for item in response_json["vat_by_code"]
    ]


def test_the_rate_comes_from_the_code_of_the_line(
    client, test_user, organization, contact, product, invoice_setting
):
    res = create(
        client,
        test_user,
        organization,
        contact,
        [line(product, 1, 100, vat_code="S02")],
    )

    assert res.status_code == 201, res.get_json()
    assert totals(res.get_json()) == (100.0, 0.0, 100.0)
    assert res.get_json()["lines"][0]["vat_code"] == "S02"


def test_every_code_has_its_own_vat(
    client, test_user, organization, contact, product, invoice_setting
):
    res = create(
        client,
        test_user,
        organization,
        contact,
        [
            line(product, 1, 100),
            line(product, 1, 50, vat_code="S02"),
            line(product, 1, 20),
        ],
    )

    assert res.status_code == 201, res.get_json()
    assert totals(res.get_json()) == (170.0, 30.0, 200.0)
    assert vat_of(res.get_json()) == [
        ("S01", 0.25, 120.0, 30.0),
        ("S02", 0.0, 50.0, 0.0),
    ]


def test_vat_is_rounded_once_per_code_and_not_once_per_line(
    client, test_user, organization, contact, product, invoice_setting
):
    res = create(
        client,
        test_user,
        organization,
        contact,
        [line(product, 1, 0.10) for _ in range(3)],
    )

    assert res.status_code == 201, res.get_json()
    # 0.075 once is 0.08; 0.025 three times would be 0.09
    assert totals(res.get_json()) == (0.30, 0.08, 0.38)


def test_a_credit_note_has_negative_vat_per_code(
    client, test_user, organization, contact, product, invoice_setting
):
    res = create(
        client, test_user, organization, contact, [line(product, 1, -100)]
    )

    assert res.status_code == 201, res.get_json()
    assert totals(res.get_json()) == (-100.0, -25.0, -125.0)
    assert vat_of(res.get_json()) == [("S01", 0.25, -100.0, -25.0)]


def test_the_vat_per_code_is_read_back_with_the_invoice(
    client, test_user, organization, contact, product, invoice_setting
):
    created = create(
        client,
        test_user,
        organization,
        contact,
        [line(product, 1, 100), line(product, 1, 50, vat_code="S21")],
    ).get_json()

    res = client.get(
        f"/invoices/{created['id']}", headers=auth_headers(test_user)
    )

    assert vat_of(res.get_json()) == [
        ("S01", 0.25, 100.0, 25.0),
        ("S21", 0.0, 50.0, 0.0),
    ]
    assert vat_of(res.get_json()) == vat_of(created)


def test_the_vat_per_code_is_the_sum_that_the_totals_show(
    client, test_user, organization, contact, product, invoice_setting
):
    res = create(
        client,
        test_user,
        organization,
        contact,
        [
            line(product, 3, 0.335),
            line(product, 7, 1.115, vat_code="S02"),
            line(product, 1, 19.99),
            line(product, 2, 0.005),
        ],
    ).get_json()

    assert res["vat_amount"] == pytest.approx(
        sum(item["vat"] for item in res["vat_by_code"])
    )
    assert res["amount"] == pytest.approx(
        sum(item["base"] for item in res["vat_by_code"])
    )


def test_a_line_without_a_vat_code_is_refused(
    client, test_user, organization, contact, product, invoice_setting
):
    bare = line(product, 1, 100)
    del bare["vat_code"]

    res = create(client, test_user, organization, contact, [bare])

    assert res.status_code == 422, res.get_json()
    assert "vat_code" in str(res.get_json()["errors"])
    assert Invoice.query.filter_by(organization_id=organization.id).count() == 0


@pytest.mark.parametrize("value", [None, 25, "", "S0000000001", ["S01"]])
def test_a_vat_code_that_is_not_a_code_is_refused(
    client, test_user, organization, contact, product, invoice_setting, value
):
    res = create(
        client,
        test_user,
        organization,
        contact,
        [line(product, 1, 100, vat_code=value)],
    )

    assert res.status_code == 422, res.get_json()
    assert Invoice.query.filter_by(organization_id=organization.id).count() == 0


@pytest.mark.parametrize(
    ("code", "message"),
    [
        ("S1", "no VAT code S1"),  # the old name is not a code
        ("S99", "no VAT code S99"),
        ("K010", "for purchases"),
        ("S83", "cannot be used yet"),  # a deferred sales code
        ("S61", "cannot be used yet"),
    ],
)
def test_a_code_an_invoice_cannot_have_is_refused_and_nothing_is_saved(
    client,
    test_user,
    organization,
    contact,
    product,
    invoice_setting,
    code,
    message,
):
    res = create(
        client,
        test_user,
        organization,
        contact,
        [line(product, 1, 100), line(product, 1, 50, vat_code=code)],
    )

    assert res.status_code == 422, res.get_json()
    assert message in res.get_json()["error"]
    assert Invoice.query.filter_by(organization_id=organization.id).count() == 0
    assert InvoiceLine.query.count() == 0


def test_the_client_cannot_send_the_id_of_the_code(
    client, test_user, organization, contact, product, invoice_setting
):
    res = create(
        client,
        test_user,
        organization,
        contact,
        [line(product, 1, 100, vat_code_id=1)],
    )

    assert res.status_code == 422, res.get_json()


def test_an_organization_that_is_not_vat_registered_can_still_invoice(
    client,
    db_session,
    test_user,
    organization,
    contact,
    product,
    invoice_setting,
):
    # It uses the code without VAT, the only one it can have
    organization.vat_period_type = None
    db_session.commit()

    res = create(
        client,
        test_user,
        organization,
        contact,
        [line(product, 1, 100, vat_code="S81")],
    )

    assert res.status_code == 201, res.get_json()
    assert totals(res.get_json()) == (100.0, 0.0, 100.0)


def test_the_code_is_stored_on_the_line(
    client, test_user, organization, contact, product, invoice_setting
):
    res = create(
        client,
        test_user,
        organization,
        contact,
        [line(product, 1, 100, vat_code="S21")],
    )

    stored = InvoiceLine.query.filter_by(invoice_id=res.get_json()["id"]).one()
    assert stored.vat_code.code == "S21"


def test_update_changes_the_vat_with_the_code_of_a_line(
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
        [saved_line(invoice["lines"][0]) | {"vat_code": "S02"}],
    )

    assert res.status_code == 200, res.get_json()
    assert totals(res.get_json()) == (100.0, 0.0, 100.0)
    assert vat_of(res.get_json()) == [("S02", 0.0, 100.0, 0.0)]


def test_update_needs_a_code_on_every_line(
    client, test_user, organization, contact, product, invoice_setting
):
    invoice = create(
        client, test_user, organization, contact, [line(product, 1, 100)]
    ).get_json()
    kept = saved_line(invoice["lines"][0])
    del kept["vat_code"]

    res = update(client, test_user, organization, invoice, contact, [kept])

    assert res.status_code == 422, res.get_json()
    assert totals(
        client.get(
            f"/invoices/{invoice['id']}", headers=auth_headers(test_user)
        ).get_json()
    ) == (100.0, 25.0, 125.0)


def test_update_refuses_a_purchase_code_and_keeps_the_invoice(
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
        [saved_line(invoice["lines"][0]) | {"vat_code": "K010"}],
    )

    assert res.status_code == 422, res.get_json()
    assert "for purchases" in res.get_json()["error"]
    assert totals(
        client.get(
            f"/invoices/{invoice['id']}", headers=auth_headers(test_user)
        ).get_json()
    ) == (100.0, 25.0, 125.0)


def test_the_lines_route_returns_the_code(
    client, test_user, organization, contact, product, invoice_setting
):
    invoice = create(
        client,
        test_user,
        organization,
        contact,
        [line(product, 1, 100, vat_code="S21")],
    ).get_json()

    res = client.get(
        f"/organizations/{organization.id}/invoices/{invoice['id']}"
        "/invoice-lines",
        headers=auth_headers(test_user),
    )

    assert res.status_code == 200
    assert [item["vat_code"] for item in res.get_json()] == ["S21"]


def test_the_tax_rate_routes_are_gone(client, test_user):
    res = client.get("/tax-rates", headers=auth_headers(test_user))

    assert res.status_code == 404
