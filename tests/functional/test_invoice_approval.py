"""Approving an invoice: it gets its number, is posted to the ledger, and is
locked (app/invoice_posting.py, docs/invoice-posting-design.md)."""

import random
from datetime import date
from decimal import Decimal

import pytest
from flask_jwt_extended import create_access_token
from sqlalchemy.exc import IntegrityError

from app.chart import apply_starter_chart
from app.ledger import LedgerConflict, LineInput, post_entry
from app.models.account import Account
from app.models.audit import AuditLog
from app.models.contact import Contact
from app.models.invoice import Invoice
from app.models.invoice_setting import InvoiceSetting
from app.models.invoiceline import InvoiceLine
from app.models.ledger import FiscalYear, JournalEntry, LedgerCounter
from app.models.organization import Organization
from app.models.product import Product
from app.models.user import User
from app.reports import trial_balance, vat_report
from app.vat_periods import settle_period

D = Decimal
LATER = date(2026, 11, 1)


def headers(user) -> dict:
    token = create_access_token(
        identity=user.email, additional_claims={"tv": user.token_version}
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def books(db_session, organization, test_user, country):
    organization.vat_period_type = "quarter"
    db_session.commit()
    apply_starter_chart(organization)
    accounts = {
        item.number: item
        for item in Account.query.filter_by(organization_id=organization.id)
    }
    setting = InvoiceSetting(
        organization_id=organization.id,
        default_account_id=accounts[1010].id,
        default_deposit_account_id=accounts[6480].id,
        invoice_no_mode="manual",
        next_invoice_no=1,
    )
    contact = Contact(
        organization_id=organization.id,
        name="Client",
        email="client@example.com",
        country_id=country.id,
    )
    product = Product(
        organization_id=organization.id, name="Consulting", unit_price=100
    )
    db_session.add_all([setting, contact, product])
    db_session.commit()
    return {
        "org": organization,
        "user": test_user,
        "headers": headers(test_user),
        "accounts": accounts,
        "setting": setting,
        "contact": contact,
        "product": product,
    }


def sequential(db_session, books):
    books["setting"].invoice_no_mode = "sequential"
    db_session.commit()


def line(books, quantity=1, price=100, code="S01", **extra):
    return {
        "product_id": books["product"].id,
        "description": "Work",
        "vat_code": code,
        "quantity": quantity,
        "unit_price": price,
        **extra,
    }


def draft(client, books, lines=None, invoice_no="1001", **extra):
    body = {
        "organization_id": books["org"].id,
        "contact_id": books["contact"].id,
        "currency_id": "DKK",
        "invoice_date": "2026-02-10",
        "duedate": "2026-02-24",
        "lines": lines if lines is not None else [line(books)],
        **extra,
    }
    if invoice_no is not None:
        body["invoice_no"] = invoice_no
    res = client.post(
        f"/organizations/{books['org'].id}/invoices",
        json=body,
        headers=books["headers"],
    )
    assert res.status_code == 201, res.get_json()
    return res.get_json()


def approve(client, books, invoice, body=None):
    return client.post(
        f"/organizations/{books['org'].id}/invoices/{invoice['id']}/approve",
        json=body or {},
        headers=books["headers"],
    )


def shown(books, entry):
    """The lines of an entry as (account number, code, part, debit, credit)."""
    numbers = {a.id: n for n, a in books["accounts"].items()}
    return [
        (
            numbers[item.account_id],
            item.vat_code.code if item.vat_code_id else None,
            item.vat_part,
            item.debit,
            item.credit,
        )
        for item in entry.lines
    ]


def entry_of(invoice_json):
    return JournalEntry.query.filter_by(
        id=invoice_json["journal_entry_id"]
    ).one()


def stored(invoice_json) -> Invoice:
    return Invoice.query.filter_by(id=invoice_json["id"]).one()


def nothing_was_posted(books, invoice, entries=0, next_number=None):
    """A refused approval leaves the invoice a draft, with no voucher and no
    number taken."""
    db_invoice = Invoice.query.filter_by(id=invoice["id"]).one()
    assert db_invoice.state == "draft"
    assert db_invoice.journal_entry_id is None
    assert JournalEntry.query.count() == entries
    assert AuditLog.query.filter_by(action="invoice.approved").count() == 0
    if next_number is not None:
        assert books["setting"].next_invoice_no == next_number


# --- what is posted --------------------------------------------------------


def test_approving_posts_the_receivable_the_sales_and_the_vat(
    client, db_session, books
):
    invoice = draft(client, books, [line(books, 10, 100)])

    res = approve(client, books, invoice)

    assert res.status_code == 200, res.get_json()
    body = res.get_json()
    assert body["state"] == "approved"
    assert body["invoice_no"] == "1001"
    assert body["voucher_no"] == 1
    assert (body["amount"], body["vat_amount"], body["gross_amount"]) == (
        1000.0,
        250.0,
        1250.0,
    )
    entry = entry_of(body)
    assert shown(books, entry) == [
        (6190, None, None, D("1250.00"), D("0.00")),
        (1010, "S01", "base", D("0.00"), D("1000.00")),
        (7680, "S01", "vat", D("0.00"), D("250.00")),
    ]
    assert entry.entry_date == date(2026, 2, 10)
    assert entry.description == "Invoice 1001"
    assert entry.source_type == "invoice"
    assert entry.source_id == invoice["id"]
    # The customer is on the receivable line
    assert entry.lines[0].contact_id == books["contact"].id


def test_the_invoice_says_who_approved_it_and_when(client, db_session, books):
    invoice = draft(client, books)

    res = approve(client, books, invoice)

    body = res.get_json()
    assert body["approved_by"] == books["user"].id
    assert body["approved_at"] is not None
    assert body["journal_entry_id"] == entry_of(body).id
    row = AuditLog.query.filter_by(
        action="invoice.approved", entity_id=invoice["id"]
    ).one()
    assert row.user_id == books["user"].id
    assert row.details["invoice_no"] == "1001"
    assert row.details["voucher_no"] == 1
    assert row.details["gross_amount"] == "125.00"


def test_several_codes_discounts_and_text_lines_are_posted_as_they_are(
    client, db_session, books
):
    invoice = draft(
        client,
        books,
        [
            line(books, 1, 1000),
            line(books, 1, 400, code="S23"),
            line(books, 1, -100),  # a discount
            line(books, 1, 0),  # a line of text
        ],
    )

    body = approve(client, books, invoice).get_json()

    entry = entry_of(body)
    assert shown(books, entry) == [
        (6190, None, None, D("1525.00"), D("0.00")),
        (1010, "S01", "base", D("0.00"), D("1000.00")),
        (1150, "S23", "base", D("0.00"), D("400.00")),
        (1010, "S01", "base", D("100.00"), D("0.00")),
        (7680, "S01", "vat", D("0.00"), D("225.00")),
    ]
    assert body["gross_amount"] == 1525.0
    assert sum(i.debit for i in entry.lines) == sum(
        i.credit for i in entry.lines
    )


def test_the_receivable_is_the_gross_amount_of_the_invoice(
    client, db_session, books
):
    invoice = draft(client, books, [line(books, 3, 0.335)])

    body = approve(client, books, invoice).get_json()

    receivable = entry_of(body).lines[0]
    assert receivable.account_id == books["accounts"][6190].id
    assert float(receivable.debit) == body["gross_amount"] == 1.26


def test_an_invoice_that_nets_to_nothing_has_no_receivable_line(
    client, db_session, books
):
    invoice = draft(client, books, [line(books, 1, 100), line(books, 1, -100)])

    body = approve(client, books, invoice).get_json()

    assert body["gross_amount"] == 0.0
    assert [item[0] for item in shown(books, entry_of(body))] == [1010, 1010]


# --- the account of a line -------------------------------------------------


@pytest.mark.parametrize(
    ("code", "account"),
    [
        ("S01", 1010),
        ("S02", 1010),
        ("S81", 1010),
        ("S82", 1010),
        ("S24", 1010),
        ("S43", 1010),
        ("S21", 1050),
        ("S22", 1050),
        ("S23", 1150),
        ("S41", 1100),
        ("S42", 1200),
    ],
)
def test_a_line_goes_to_the_sales_account_of_its_vat_code(
    client, db_session, books, code, account
):
    invoice = draft(client, books, [line(books, 1, 100, code=code)])

    body = approve(client, books, invoice).get_json()

    assert shown(books, entry_of(body))[1][0] == account


def test_the_account_of_the_product_comes_first(client, db_session, books):
    books["product"].account_id = books["accounts"][1250].id
    db_session.commit()
    invoice = draft(client, books, [line(books, 1, 100, code="S23")])

    body = approve(client, books, invoice).get_json()

    assert shown(books, entry_of(body))[1][0] == 1250


def test_the_default_account_of_the_settings_is_the_last_resort(
    client, db_session, books
):
    books["accounts"][1010].system_role = None
    books["setting"].default_account_id = books["accounts"][1250].id
    db_session.commit()
    invoice = draft(client, books)

    body = approve(client, books, invoice).get_json()

    assert shown(books, entry_of(body))[1][0] == 1250


def test_a_chart_without_the_account_for_the_code_stops_the_approval(
    client, db_session, books
):
    books["accounts"][1150].system_role = None
    db_session.commit()
    invoice = draft(client, books, [line(books, 1, 100, code="S23")])

    res = approve(client, books, invoice)

    assert res.status_code == 409
    assert "sales_eu_services" in res.get_json()["error"]
    nothing_was_posted(books, invoice)


def test_a_chart_without_the_receivables_account_stops_the_approval(
    client, db_session, books
):
    books["accounts"][6190].system_role = None
    db_session.commit()
    invoice = draft(client, books)

    res = approve(client, books, invoice)

    assert res.status_code == 409
    assert "receivables" in res.get_json()["error"]
    nothing_was_posted(books, invoice)


# --- an organization that is not VAT-registered ----------------------------


def unregister(db_session, books):
    books["org"].vat_period_type = None
    db_session.commit()


def test_an_organization_without_vat_posts_its_invoice_without_vat_codes(
    client, db_session, books
):
    unregister(db_session, books)
    invoice = draft(client, books, [line(books, 2, 500, code="S81")])

    res = approve(client, books, invoice)

    assert res.status_code == 200, res.get_json()
    body = res.get_json()
    assert body["vat_amount"] == 0.0
    assert shown(books, entry_of(body)) == [
        (6190, None, None, D("1000.00"), D("0.00")),
        (1010, None, None, D("0.00"), D("1000.00")),
    ]


@pytest.mark.parametrize("code", ["S01", "S02", "S21", "S82"])
def test_an_organization_without_vat_cannot_save_an_invoice_with_vat(
    client, db_session, books, code
):
    unregister(db_session, books)

    res = client.post(
        f"/organizations/{books['org'].id}/invoices",
        json={
            "organization_id": books["org"].id,
            "contact_id": books["contact"].id,
            "invoice_no": "1001",
            "currency_id": "DKK",
            "invoice_date": "2026-02-10",
            "duedate": "2026-02-24",
            "lines": [line(books, code=code)],
        },
        headers=books["headers"],
    )

    assert res.status_code == 422
    assert "not VAT-registered" in res.get_json()["error"]
    assert Invoice.query.count() == 0


def test_a_draft_that_has_vat_is_refused_when_the_organization_has_none(
    client, db_session, books
):
    invoice = draft(client, books)  # while it was registered
    unregister(db_session, books)

    res = approve(client, books, invoice)

    assert res.status_code == 422
    assert "not VAT-registered" in res.get_json()["error"]
    nothing_was_posted(books, invoice)


def test_a_draft_cannot_be_updated_to_vat_when_the_organization_has_none(
    client, db_session, books
):
    invoice = draft(client, books, [line(books, code="S81")])
    unregister(db_session, books)
    invoice_body = {
        "organization_id": books["org"].id,
        "contact_id": books["contact"].id,
        "invoice_no": "1001",
        "currency_id": "DKK",
        "invoice_date": "2026-02-10",
        "duedate": "2026-02-24",
        "lines": [line(books, code="S01")],
    }

    res = client.put(
        f"/organizations/{books['org'].id}/invoices/{invoice['id']}",
        json=invoice_body,
        headers=books["headers"],
    )

    assert res.status_code == 422


# --- the number ------------------------------------------------------------


def test_a_draft_in_sequential_mode_has_no_number_and_a_sent_one_is_not_used(
    client, db_session, books
):
    sequential(db_session, books)

    invoice = draft(client, books, invoice_no="9999")

    assert invoice["invoice_no"] is None
    assert stored(invoice).invoice_no is None


def test_sequential_numbers_are_taken_when_the_invoices_are_approved(
    client, db_session, books
):
    sequential(db_session, books)
    first = draft(client, books, invoice_no=None)
    second = draft(client, books, invoice_no=None)

    # The second draft is approved first: the number follows the approval
    one = approve(client, books, second).get_json()
    two = approve(client, books, first).get_json()

    assert (one["invoice_no"], two["invoice_no"]) == ("1", "2")
    db_session.refresh(books["setting"])
    assert books["setting"].next_invoice_no == 3


def test_a_deleted_draft_leaves_no_gap(client, db_session, books):
    sequential(db_session, books)
    doomed = draft(client, books, invoice_no=None)
    kept = draft(client, books, invoice_no=None)
    deleted = client.delete(
        f"/organizations/{books['org'].id}/invoices/{doomed['id']}",
        headers=books["headers"],
    )
    assert deleted.status_code == 200

    body = approve(client, books, kept).get_json()

    assert body["invoice_no"] == "1"


def test_a_refused_approval_gives_the_number_back(client, db_session, books):
    sequential(db_session, books)
    refused = draft(client, books, invoice_no=None, invoice_date="2099-01-01")
    fine = draft(client, books, invoice_no=None)

    assert approve(client, books, refused).status_code == 422
    body = approve(client, books, fine).get_json()

    assert body["invoice_no"] == "1"
    db_session.refresh(books["setting"])
    assert books["setting"].next_invoice_no == 2


def test_the_numbers_have_no_gap_whatever_is_refused(client, db_session, books):
    sequential(db_session, books)
    generator = random.Random(7)
    approved = []
    for _ in range(14):
        date_ = generator.choice(["2026-02-10", "2099-01-01", "2026-03-01"])
        currency = generator.choice(["DKK", "DKK", "EUR"])
        invoice = draft(
            client,
            books,
            invoice_no=None,
            invoice_date=date_,
            currency_id=currency,
        )
        res = approve(client, books, invoice)
        if res.status_code == 200:
            approved.append(int(res.get_json()["invoice_no"]))
        else:
            assert res.status_code == 422

    assert approved == list(range(1, len(approved) + 1))
    assert len(approved) > 0


def test_manual_mode_needs_a_number_and_takes_the_one_given(
    client, db_session, books
):
    invoice = draft(client, books, invoice_no=None)

    refused = approve(client, books, invoice)
    assert refused.status_code == 422
    assert "needs a number" in refused.get_json()["error"]
    nothing_was_posted(books, invoice)

    done = approve(client, books, invoice, {"invoice_no": "INV-7"})
    assert done.status_code == 200
    assert done.get_json()["invoice_no"] == "INV-7"


def test_manual_mode_uses_the_number_of_the_draft(client, db_session, books):
    invoice = draft(client, books, invoice_no="A-12")

    body = approve(client, books, invoice).get_json()

    assert body["invoice_no"] == "A-12"


def test_a_number_that_is_taken_is_refused_in_manual_mode(
    client, db_session, books
):
    first = draft(client, books, invoice_no="1001")
    assert approve(client, books, first).status_code == 200
    second = draft(client, books, invoice_no="1002")

    res = approve(client, books, second, {"invoice_no": "1001"})

    assert res.status_code == 409
    assert "already used" in res.get_json()["error"]


def test_a_numeric_number_moves_the_next_number_in_manual_mode(
    client, db_session, books
):
    invoice = draft(client, books, invoice_no="1001")

    approve(client, books, invoice)

    db_session.refresh(books["setting"])
    assert books["setting"].next_invoice_no == 1002


def test_a_taken_number_in_sequential_mode_points_at_the_settings(
    client, db_session, books
):
    sequential(db_session, books)
    other = Invoice(
        organization_id=books["org"].id,
        contact_id=books["contact"].id,
        invoice_no="1",
        invoice_date=date(2026, 1, 1),
        duedate=date(2026, 1, 15),
    )
    db_session.add(other)
    db_session.commit()
    invoice = draft(client, books, invoice_no=None)

    res = approve(client, books, invoice)

    assert res.status_code == 409
    assert "next number" in res.get_json()["error"]
    db_session.refresh(books["setting"])
    assert books["setting"].next_invoice_no == 1


# --- what is refused -------------------------------------------------------


def test_an_approved_invoice_cannot_be_approved_again(
    client, db_session, books
):
    invoice = draft(client, books)
    assert approve(client, books, invoice).status_code == 200
    entries = JournalEntry.query.count()

    res = approve(client, books, invoice)

    assert res.status_code == 409
    assert "already approved" in res.get_json()["error"]
    assert JournalEntry.query.count() == entries


def test_an_invoice_dated_in_the_future_is_refused(client, db_session, books):
    invoice = draft(client, books, invoice_date="2099-01-01")

    res = approve(client, books, invoice)

    assert res.status_code == 422
    assert "future" in res.get_json()["error"]
    nothing_was_posted(books, invoice)


def test_an_invoice_in_another_currency_is_refused(client, db_session, books):
    invoice = draft(client, books, currency_id="EUR")

    res = approve(client, books, invoice)

    assert res.status_code == 422
    assert "DKK" in res.get_json()["error"]
    nothing_was_posted(books, invoice)


def test_an_invoice_with_only_lines_of_0_has_nothing_to_book(
    client, db_session, books
):
    invoice = draft(client, books, [line(books, 1, 0), line(books, 5, 0)])

    res = approve(client, books, invoice)

    assert res.status_code == 422
    assert "nothing to book" in res.get_json()["error"]
    nothing_was_posted(books, invoice)


def test_an_invoice_in_a_closed_fiscal_year_is_refused(
    client, db_session, books
):
    invoice = draft(client, books)
    post_entry(
        books["org"].id,
        books["user"].id,
        date(2026, 1, 5),
        "Opens the year",
        [
            LineInput(books["accounts"][6480].id, debit=D("1")),
            LineInput(books["accounts"][1010].id, credit=D("1")),
        ],
    )
    FiscalYear.query.filter_by(
        organization_id=books["org"].id
    ).one().status = "closed"
    db_session.commit()
    counter = LedgerCounter.query.filter_by(
        organization_id=books["org"].id
    ).one()
    next_voucher = counter.next_voucher_no

    res = approve(client, books, invoice)

    assert res.status_code == 409
    assert "closed" in res.get_json()["error"]
    nothing_was_posted(books, invoice, entries=1, next_number=1)
    db_session.refresh(counter)
    assert counter.next_voucher_no == next_voucher


def test_an_invoice_dated_in_a_settled_vat_period_is_refused(
    client, db_session, books
):
    approved = draft(client, books, invoice_no="1001")
    assert approve(client, books, approved).status_code == 200
    settle_period(books["org"].id, books["user"].id, LATER)
    late = draft(client, books, invoice_no="1002", invoice_date="2026-03-20")
    entries = JournalEntry.query.count()

    res = approve(client, books, late)

    assert res.status_code == 409
    assert "is settled" in res.get_json()["error"]
    assert JournalEntry.query.count() == entries
    db_session.refresh(books["setting"])
    assert books["setting"].next_invoice_no == 1002


def test_an_invoice_dated_after_a_settled_period_is_approved(
    client, db_session, books
):
    approved = draft(client, books, invoice_no="1001")
    approve(client, books, approved)
    settle_period(books["org"].id, books["user"].id, LATER)
    later = draft(client, books, invoice_no="1002", invoice_date="2026-04-01")

    res = approve(client, books, later)

    assert res.status_code == 200, res.get_json()


def test_without_invoice_settings_an_invoice_cannot_be_approved(
    client, db_session, books
):
    invoice = draft(client, books)
    db_session.delete(books["setting"])
    db_session.commit()

    res = approve(client, books, invoice)

    assert res.status_code == 409
    assert "settings" in res.get_json()["error"].lower()


def test_an_invoice_that_is_not_found_is_404(client, db_session, books):
    res = client.post(
        f"/organizations/{books['org'].id}/invoices/99999/approve",
        json={},
        headers=books["headers"],
    )

    assert res.status_code == 404


def test_the_approval_needs_a_login(client, books):
    res = client.post(
        f"/organizations/{books['org'].id}/invoices/1/approve", json={}
    )

    assert res.status_code == 401


def test_a_bad_number_in_the_request_is_refused(client, db_session, books):
    invoice = draft(client, books)

    res = approve(client, books, invoice, {"invoice_no": "x" * 101})

    assert res.status_code == 422


def test_another_organization_cannot_approve_my_invoice(
    client, db_session, books, country
):
    invoice = draft(client, books)
    other = Organization(
        name="Other ApS",
        slug="other-aps",
        country_id=country.id,
        email="other@example.com",
        logo="",
    )
    db_session.add(other)
    db_session.flush()
    user = User(
        organization_id=other.id,
        password_plaintext="password123",
        name="Other",
        email="other@example.com",
        otp_secret=User.generate_otp_secret(),
    )
    db_session.add(user)
    db_session.commit()

    res = client.post(
        f"/organizations/{books['org'].id}/invoices/{invoice['id']}/approve",
        json={},
        headers=headers(user),
    )

    assert res.status_code == 404
    assert stored(invoice).state == "draft"


# --- locked ----------------------------------------------------------------


def approved(client, books):
    invoice = draft(client, books)
    return approve(client, books, invoice).get_json()


def test_an_approved_invoice_cannot_be_updated(client, db_session, books):
    invoice = approved(client, books)
    body = {
        "organization_id": books["org"].id,
        "contact_id": books["contact"].id,
        "invoice_no": "1001",
        "currency_id": "DKK",
        "invoice_date": "2026-02-10",
        "duedate": "2026-02-24",
        "lines": [line(books, 99, 100)],
    }

    res = client.put(
        f"/organizations/{books['org'].id}/invoices/{invoice['id']}",
        json=body,
        headers=books["headers"],
    )

    assert res.status_code == 409
    assert "credit note" in res.get_json()["error"]
    assert float(stored(invoice).gross_amount) == invoice["gross_amount"]
    assert InvoiceLine.query.filter_by(invoice_id=invoice["id"]).count() == 1


def test_an_approved_invoice_cannot_be_deleted(client, db_session, books):
    invoice = approved(client, books)

    res = client.delete(
        f"/organizations/{books['org'].id}/invoices/{invoice['id']}",
        headers=books["headers"],
    )

    assert res.status_code == 409
    assert Invoice.query.filter_by(id=invoice["id"]).count() == 1
    assert InvoiceLine.query.filter_by(invoice_id=invoice["id"]).count() == 1


def test_a_line_of_an_approved_invoice_cannot_be_deleted(
    client, db_session, books
):
    invoice = approved(client, books)
    line_id = InvoiceLine.query.filter_by(invoice_id=invoice["id"]).one().id

    res = client.delete(
        f"/organizations/{books['org'].id}/invoices/{invoice['id']}"
        f"/invoice-lines/{line_id}",
        headers=books["headers"],
    )

    assert res.status_code == 409
    assert InvoiceLine.query.filter_by(invoice_id=invoice["id"]).count() == 1


def test_an_approved_invoice_can_be_marked_as_sent(client, db_session, books):
    invoice = approved(client, books)

    res = client.patch(
        f"/invoices/{invoice['id']}/mark-as-sent",
        json={"is_sent": True},
        headers=books["headers"],
    )

    assert res.status_code == 200, res.get_json()
    assert res.get_json()["is_sent"] is True
    assert stored(invoice).state == "approved"


def test_a_draft_cannot_be_marked_as_sent(client, db_session, books):
    invoice = draft(client, books)

    res = client.patch(
        f"/invoices/{invoice['id']}/mark-as-sent",
        json={"is_sent": True},
        headers=books["headers"],
    )

    assert res.status_code == 409
    assert stored(invoice).is_sent is False


@pytest.mark.parametrize(
    "field",
    [
        {"state": "approved"},
        {"is_paid": True},
        {"is_sent": True},
        {"journal_entry_id": 1},
        {"approved_by": 1},
        {"approved_at": "2026-01-01T00:00:00"},
    ],
)
def test_a_new_invoice_cannot_start_approved_or_paid(
    client, db_session, books, field
):
    res = client.post(
        f"/organizations/{books['org'].id}/invoices",
        json={
            "organization_id": books["org"].id,
            "contact_id": books["contact"].id,
            "invoice_no": "1001",
            "currency_id": "DKK",
            "invoice_date": "2026-02-10",
            "duedate": "2026-02-24",
            "lines": [line(books)],
            **field,
        },
        headers=books["headers"],
    )

    assert res.status_code == 422
    assert Invoice.query.count() == 0


def test_the_database_wants_an_approved_invoice_to_have_its_voucher(
    db_session, books
):
    invoice = Invoice(
        organization_id=books["org"].id,
        contact_id=books["contact"].id,
        invoice_no="1",
        invoice_date=date(2026, 1, 1),
        duedate=date(2026, 1, 15),
        state="approved",
    )
    db_session.add(invoice)

    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_the_database_refuses_a_state_that_does_not_exist(db_session, books):
    invoice = Invoice(
        organization_id=books["org"].id,
        contact_id=books["contact"].id,
        invoice_no="1",
        invoice_date=date(2026, 1, 1),
        duedate=date(2026, 1, 15),
        state="paid",
    )
    db_session.add(invoice)

    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_a_number_is_used_by_one_invoice_only(db_session, books):
    for _ in range(2):
        db_session.add(
            Invoice(
                organization_id=books["org"].id,
                contact_id=books["contact"].id,
                invoice_no="1",
                invoice_date=date(2026, 1, 1),
                duedate=date(2026, 1, 15),
            )
        )

    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_drafts_without_a_number_do_not_collide(db_session, books):
    for _ in range(3):
        db_session.add(
            Invoice(
                organization_id=books["org"].id,
                contact_id=books["contact"].id,
                invoice_date=date(2026, 1, 1),
                duedate=date(2026, 1, 15),
            )
        )

    db_session.flush()

    assert Invoice.query.filter(Invoice.invoice_no.is_(None)).count() == 3


def test_an_invoice_has_at_most_400_lines(client, db_session, books):
    res = client.post(
        f"/organizations/{books['org'].id}/invoices",
        json={
            "organization_id": books["org"].id,
            "contact_id": books["contact"].id,
            "invoice_no": "1001",
            "currency_id": "DKK",
            "invoice_date": "2026-02-10",
            "duedate": "2026-02-24",
            "lines": [line(books) for _ in range(401)],
        },
        headers=books["headers"],
    )

    assert res.status_code == 422
    assert "at most 400" in res.get_json()["error"]


def test_an_invoice_of_400_lines_can_be_approved(client, db_session, books):
    invoice = draft(client, books, [line(books, 1, 1) for _ in range(400)])

    res = approve(client, books, invoice)

    assert res.status_code == 200, res.get_json()
    # One line each, the receivable and the VAT of the one code
    assert len(entry_of(res.get_json()).lines) == 402


# --- the voucher of an invoice ---------------------------------------------


def test_the_voucher_of_an_invoice_cannot_be_reversed_from_the_journal(
    client, db_session, books
):
    invoice = approved(client, books)

    res = client.post(
        f"/journal-entries/{invoice['journal_entry_id']}/reverse",
        json={},
        headers=books["headers"],
    )

    assert res.status_code == 409
    assert "credit note" in res.get_json()["error"]
    assert (
        JournalEntry.query.filter_by(
            reverses_entry_id=invoice["journal_entry_id"]
        ).count()
        == 0
    )


def test_the_service_refuses_to_reverse_it_too(db_session, books):
    from app.ledger import reverse_entry

    entry = post_entry(
        books["org"].id,
        books["user"].id,
        date(2026, 2, 10),
        "A voucher of a payment",
        [
            LineInput(books["accounts"][6480].id, debit=D("1")),
            LineInput(books["accounts"][6190].id, credit=D("1")),
        ],
        source_type="payment",
    )

    with pytest.raises(LedgerConflict):
        reverse_entry(books["org"].id, books["user"].id, entry.id)


def test_a_manual_voucher_can_still_be_reversed(client, db_session, books):
    entry = post_entry(
        books["org"].id,
        books["user"].id,
        date(2026, 2, 10),
        "A manual voucher",
        [
            LineInput(books["accounts"][6480].id, debit=D("1")),
            LineInput(books["accounts"][1010].id, credit=D("1")),
        ],
    )
    db_session.commit()

    res = client.post(
        f"/journal-entries/{entry.id}/reverse",
        json={},
        headers=books["headers"],
    )

    assert res.status_code == 201


# --- the books agree with the invoices -------------------------------------


def test_the_vat_report_gives_the_vat_of_the_invoices(
    client, db_session, books
):
    for number, price in (("1001", 1000), ("1002", 400)):
        invoice = draft(
            client, books, [line(books, 1, price)], invoice_no=number
        )
        approve(client, books, invoice)
    credit_free = draft(
        client, books, [line(books, 1, 300, code="S23")], invoice_no="1003"
    )
    approve(client, books, credit_free)

    report = vat_report(books["org"].id, date(2026, 1, 1), date(2026, 3, 31))

    assert report["sales_vat"] == D("350.00")
    assert report["boxes"]["b_services"] == D("300.00")
    assert report["ledger_check"]["ties"] is True
    assert report["ledger_check"]["uncoded_lines"] == []


CODES = ["S01", "S01", "S02", "S21", "S23", "S41", "S81"]


@pytest.mark.parametrize("seed", range(30))
def test_random_invoices_are_posted_as_their_totals_say(
    client, db_session, books, seed
):
    generator = random.Random(seed)
    invoices = []
    for number in range(generator.randint(1, 6)):
        lines = [
            line(
                books,
                generator.choice([1, 2, 3, 0.5, 7]),
                generator.choice([100, 0.335, 19.99, 1250, -40, 0]),
                code=generator.choice(CODES),
            )
            for _ in range(generator.randint(1, 5))
        ]
        if all(item["unit_price"] == 0 for item in lines):
            lines[0]["unit_price"] = 10
        day = f"2026-0{generator.randint(1, 3)}-{generator.randint(10, 28)}"
        invoice = draft(
            client,
            books,
            lines,
            invoice_no=str(2000 + number),
            invoice_date=day,
        )
        body = approve(client, books, invoice).get_json()
        invoices.append(body)

    for body in invoices:
        entry = entry_of(body)
        # The entry balances, and the receivable line is the gross amount
        assert sum(i.debit for i in entry.lines) == sum(
            i.credit for i in entry.lines
        )
        receivable = [
            i for i in entry.lines if i.account_id == books["accounts"][6190].id
        ]
        net = sum((i.debit - i.credit for i in receivable), D("0"))
        assert float(net) == body["gross_amount"]
        # The VAT lines are the VAT of each code of the invoice
        vat_lines = {
            i.vat_code.code: float(i.credit - i.debit)
            for i in entry.lines
            if i.vat_part == "vat"
        }
        expected = {
            item["code"]: item["vat"]
            for item in body["vat_by_code"]
            if item["vat"]
        }
        assert vat_lines == expected

    total_gross = sum(D(str(body["gross_amount"])) for body in invoices)
    balances = {
        item["number"]: item["closing_balance"]
        for item in trial_balance(books["org"].id)["accounts"]
    }
    assert balances.get(6190, D(0)) == total_gross
    assert trial_balance(books["org"].id)["balanced"]
    report = vat_report(books["org"].id, date(2026, 1, 1), date(2026, 3, 31))
    assert report["ledger_check"]["ties"] is True
    assert report["sales_vat"] == sum(
        (
            D(str(item["vat"]))
            for body in invoices
            for item in body["vat_by_code"]
        ),
        D("0"),
    )
